"""Unit tests for the ingest layer. They need no network: HTTP calls go to a stub session."""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from ingest.bronze import BronzeWriter, safe_key
from ingest.http import BudgetExceeded, HostPolicy, HttpClient, HttpError
from ingest.parsers import prometheus, revenue_page
from ingest.pipeline import Context, Dataset, Skip, run
from ingest.settings import load_dotenv, secret
from ingest.sources.neardata import tally


class FakeResponse:
    def __init__(self, status=200, body=b"{}", headers=None):
        self.status_code, self.content, self.headers = status, body, headers or {}
        self.url = "https://example.test/x"
        self.text = body.decode()


class FakeSession:
    def __init__(self, replies):
        self.replies = list(replies)
        self.headers = {}
        self.calls = []

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self.replies.pop(0)


def client(replies, **policy) -> HttpClient:
    c = HttpClient(policies={"example.test": HostPolicy(**policy)}, log=lambda m: None)
    c.session = FakeSession(replies)
    c._sleep = lambda *a, **k: None
    return c


def test_http_returns_exact_bytes():
    c = client([FakeResponse(body=b'{"a": 1}')])
    assert c.get("https://example.test/x").content == b'{"a": 1}'


def test_http_retries_429_and_server_errors():
    c = client([FakeResponse(429), FakeResponse(503), FakeResponse(200, b"ok")])
    assert c.get("https://example.test/x").content == b"ok"
    assert len(c.session.calls) == 3


def test_http_does_not_retry_client_errors():
    c = client([FakeResponse(404, b"nope"), FakeResponse(200)])
    with pytest.raises(HttpError) as e:
        c.get("https://example.test/x")
    assert e.value.status == 404 and len(c.session.calls) == 1


def test_http_gives_up_after_retries():
    c = client([FakeResponse(429) for _ in range(3)])
    with pytest.raises(HttpError):
        c.get("https://example.test/x", retries=3)


def test_http_daily_budget_stops_calls():
    c = client([FakeResponse(), FakeResponse()], daily_budget=1)
    c.get("https://example.test/x")
    with pytest.raises(BudgetExceeded):
        c.get("https://example.test/x")


def test_bronze_is_deterministic_and_hashes_raw_bytes(tmp_path):
    w = BronzeWriter("2026-11-01", root=tmp_path)
    p1 = w.save("src", "ds", "key", b'{"x":1}', url="https://example.test")
    first = p1.read_bytes()
    p2 = w.save("src", "ds", "key", b'{"x":1}', url="https://example.test")
    assert p2.read_bytes() == first
    assert gzip.decompress(first) == b'{"x":1}'
    w.flush()
    entry = json.loads((tmp_path / "_manifest" / "dt=2026-11-01.jsonl").read_text())
    assert entry["sha256"] == hashlib.sha256(b'{"x":1}').hexdigest()
    assert entry["path"] == "src/ds/dt=2026-11-01/key.json.gz"


def test_bronze_parallel_writers_keep_each_others_lines(tmp_path):
    a, b = BronzeWriter("2026-11-01", root=tmp_path), BronzeWriter("2026-11-01", root=tmp_path)
    a.save("s", "d", "a", b"1", url="u")
    b.save("s", "d", "b", b"2", url="u")
    a.flush()
    b.flush()
    lines = (tmp_path / "_manifest" / "dt=2026-11-01.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_safe_key_blocks_path_tricks():
    assert "/" not in safe_key("../../etc/passwd")
    assert safe_key("buybacks.multisignature.near") == "buybacks.multisignature.near"


def test_runner_survives_a_failing_dataset(tmp_path, monkeypatch):
    monkeypatch.setattr("ingest.pipeline.BRONZE", tmp_path)
    monkeypatch.setattr("ingest.pipeline.BronzeWriter", lambda snapshot: BronzeWriter(snapshot, root=tmp_path))

    def boom(ctx):
        raise ValueError("bug in one source")

    def skip(ctx):
        raise Skip("not today")

    def fine(ctx):
        ctx.bronze.save("s", "d", "k", b"1", url="u")

    results = run("2026-11-01", [Dataset("a", "boom", boom), Dataset("a", "skip", skip), Dataset("a", "fine", fine),
                                 Dataset("a", "keyed", fine, requires=("THIS_KEY_IS_NOT_SET",))])
    assert results["a/boom"]["status"] == "failed"
    assert results["a/skip"]["status"] == "skipped"
    assert results["a/fine"]["status"] == "ok"
    assert results["a/keyed"]["status"] == "skipped" and "THIS_KEY_IS_NOT_SET" in results["a/keyed"]["detail"]


def test_dotenv_ignores_comments_and_blanks(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("# comment\nNEAR_THESIS_TEST_A=hello   # inline comment\nNEAR_THESIS_TEST_B=\n")
    monkeypatch.delenv("NEAR_THESIS_TEST_A", raising=False)
    monkeypatch.delenv("NEAR_THESIS_TEST_B", raising=False)
    load_dotenv(env)
    assert secret("NEAR_THESIS_TEST_A") == "hello"
    assert secret("NEAR_THESIS_TEST_B") is None


def _page(payload: dict) -> str:
    body = 'x:["$","$L1",null,' + json.dumps(payload, separators=(",", ":")) + "]"
    return "<html>Updated · Nov 01, 2026<script>self.__next_f.push([1," + json.dumps(body) + "])</script></html>"


FULL_PAGE = {
    "stats": [{"label": "Total", "value": "$$1"}],
    "tvlChartSeries": [{"date": "2026-10-31", "value": 1.5}],
    "emissionsMonthly": [{"date": "2026-10-01", "value": 18}],
    "absoluteRevEmissions": [{"date": "2026-10-31", "emissionsNear": 10}],
    "revenueSeries": [{"period_month": "2026-10-01", "revenue_usd": 5}],
    "intentVolumeSeries": [{"date_at": "2026-10-31", "volume_usd": 7}],
    "totalFeesSeries": [{"date_at": "2026-10-31", "fees_usd": 3}],
    "rows": [{"name": "a.near", "nearAmount": 1}],
    "capture": {"pp_fe_all_time": 0.1, "pp_fe_d30": 0.2, "is_stale": 0},
}


def test_revenue_page_parser_reads_embedded_series():
    parsed = revenue_page.parse(_page(FULL_PAGE))
    assert parsed["totalFeesSeries"][0]["fees_usd"] == 3
    assert parsed["captureRates"]["pp_fe_d30"] == 0.2
    assert parsed["rows"][0]["name"] == "a.near"


def test_revenue_page_parser_fails_loudly_when_a_series_disappears():
    broken = {k: v for k, v in FULL_PAGE.items() if k != "totalFeesSeries"}
    with pytest.raises(ValueError, match="totalFeesSeries"):
        revenue_page.parse(_page(broken))


def test_revenue_page_parser_fails_without_a_payload():
    with pytest.raises(ValueError):
        revenue_page.parse("<html>redesigned</html>")


def test_prometheus_parser_skips_comments_and_labels():
    text = "# HELP x\nmetapool_tvl 21234664.61\nlabelled{a=\"b\"} 3\nnot_a_number abc\n"
    assert prometheus.parse(text) == {"metapool_tvl": 21234664.61}


def _block(shards):
    return {"shards": shards}


def test_tally_counts_per_receiver_and_keeps_big_burn_exact():
    block = _block([{
        "chunk": {"transactions": [
            {"transaction": {"signer_id": "alice.near", "receiver_id": "intents.near", "actions": [{"Delegate": {}}]}},
            {"transaction": {"signer_id": "bob.near", "receiver_id": "intents.near", "actions": ["CreateAccount"]}},
        ]},
        "receipt_execution_outcomes": [
            {"receipt": {"receiver_id": "wrap.near"}, "execution_outcome": {"outcome": {"gas_burnt": 5, "tokens_burnt": "1000000000000000000000000"}}},
            {"receipt": {"receiver_id": "intents.near"}, "execution_outcome": {"outcome": {"gas_burnt": 7, "tokens_burnt": "1"}}},
        ],
    }])
    s = tally([block, _block([{"chunk": None, "receipt_execution_outcomes": None}])])
    assert (s["blocks_sampled"], s["txns_sampled"], s["receipts_sampled"]) == (2, 2, 2)
    by_account = {r["account_id"]: r for r in s["receivers"]}
    assert by_account["intents.near"]["txns"] == 2
    assert by_account["intents.near"]["distinct_signers"] == 2
    assert by_account["wrap.near"]["tokens_burnt_yocto"] == "1000000000000000000000000"
    assert s["action_kinds"] == {"Delegate": 1, "CreateAccount": 1}
    assert s["receivers"][0]["account_id"] == "intents.near"


def test_context_state_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr("ingest.pipeline.STATE", tmp_path)
    ctx = Context("2026-11-01", None, None)
    assert ctx.load_state("x", {"default": True}) == {"default": True}
    ctx.save_state("x", {"cursor": 5})
    assert ctx.load_state("x") == {"cursor": 5}


def test_requirements_lock_pins_every_package():
    lock = Path(__file__).resolve().parents[1] / "requirements.lock"
    lines = [line for line in lock.read_text().splitlines() if line and not line.startswith("#")]
    assert lines and all("==" in line for line in lines)


def test_block_day_wanted_is_monthly_then_daily():
    from datetime import date

    from ingest.sources.rpc import DAILY_FROM, MONTHLY_FROM, _days_wanted

    days = _days_wanted(date(2025, 1, 3))
    assert days[0] == MONTHLY_FROM
    assert days[1] == date(2020, 9, 1)
    assert days[-3:] == [DAILY_FROM, date(2025, 1, 2), date(2025, 1, 3)]
    assert days == sorted(set(days))


def test_rpc_error_as_http_422_means_no_result():
    from ingest.sources.rpc import _existing_header

    missing = FakeResponse(422, b'{"jsonrpc":"2.0","error":{"cause":{"name":"UNKNOWN_BLOCK"}}}')
    found = FakeResponse(200, b'{"jsonrpc":"2.0","result":{"header":{"height":12}}}')
    ctx = Context("2026-11-01", client([missing, found]), None)
    ctx.http.policies["archival-rpc.mainnet.fastnear.com"] = HostPolicy()
    assert _existing_header(ctx, 11)["height"] == 12


DAY_START = 1793404800  # 2026-10-31 00:00:00 UTC


def _swap(ts, address, status="SUCCESS", amount=100.0, referral="swapkit", fee=50, recipient="partner.near", origin="in", destination="out"):
    return {"createdAtTimestamp": ts, "depositAddress": address, "depositMemo": None, "depositAddressAndMemo": address, "status": status,
            "referral": referral, "originAsset": origin, "destinationAsset": destination, "amountInUsd": str(amount), "amountOutUsd": str(amount * 0.99),
            "appFees": [{"recipient": recipient, "fee": fee}], "senders": [f"sender-{address}"], "recipient": f"recipient-{address}",
            "depositType": "ORIGIN_CHAIN", "recipientType": "DESTINATION_CHAIN"}


def _explorer_context(tmp_path, monkeypatch, pages, snapshot="2026-11-01"):
    from ingest import sources  # noqa: F401
    from ingest.sources import intents

    monkeypatch.setattr("ingest.pipeline.STATE", tmp_path)
    monkeypatch.setattr(intents, "EXPLORER_PAGE_SIZE", 2)
    monkeypatch.setenv("INTENTS_EXPLORER_JWT", "test-value")
    http = client([FakeResponse(200, json.dumps(p).encode()) for p in pages])
    http.policies["explorer.near-intents.org"] = HostPolicy()
    return intents, Context(snapshot, http, BronzeWriter(snapshot, root=tmp_path / "bronze")), http


def test_explorer_tally_keeps_totals_and_no_wallet_address():
    from ingest.sources import intents

    rows = [_swap(1, "a", amount=2000.0), _swap(2, "b", amount=500.0, fee=20, recipient="buybacks.multisignature.near"),
            _swap(3, "c", status="REFUNDED", amount=300.0), _swap(4, "d", amount=50.0, referral=None, origin="tiny")]
    tally = intents.tally_day(date(2026, 10, 31), rows, 1, {"buybacks.multisignature.near"})
    assert tally["swaps"] == 4 and tally["senders"] == 3 and tally["recipients"] == 3
    swapkit = next(c for c in tally["channels"] if c["referral"] == "swapkit" and c["status"] == "SUCCESS")
    assert swapkit["swaps"] == 2 and swapkit["amount_in_usd"] == 2500.0 and swapkit["app_fee_usd"] == pytest.approx(11.0)
    assert {c["status"] for c in tally["channels"]} == {"SUCCESS", "REFUNDED"}
    assert {p["origin_asset"]: p["amount_in_usd"] for p in tally["pairs"]} == {"in": 2500.0, "(other)": 50.0}
    assert {s["bucket"]: s["swaps"] for s in tally["sizes"]} == {"1k_to_10k": 1, "100_to_1k": 1, "under_100": 1}
    assert tally["routes"] == [{"deposit_type": "ORIGIN_CHAIN", "recipient_type": "DESTINATION_CHAIN", "swaps": 3, "amount_in_usd": 2550.0}]
    assert {r["recipient"]: r["fee_usd"] for r in tally["fee_recipients"]} == {"buybacks.multisignature.near": pytest.approx(1.0), "(other)": pytest.approx(10.25)}
    text = json.dumps(tally)
    assert not any(secret_part in text for secret_part in ("sender-", "recipient-", "partner.near"))


def test_explorer_walks_each_day_and_stops_at_the_page_budget(tmp_path, monkeypatch):
    previous = DAY_START - 86400
    pages = [[_swap(DAY_START + 9, "a"), _swap(DAY_START + 8, "b")],
             [_swap(DAY_START + 7, "c"), _swap(DAY_START - 1, "outside")],
             [],
             [_swap(previous + 5, "d")],
             ]
    intents, ctx, http = _explorer_context(tmp_path, monkeypatch, pages)
    monkeypatch.setattr(intents, "EXPLORER_PAGES_PER_RUN", 4)
    intents.explorer_daily_tally(ctx)
    state = ctx.load_state("intents_explorer__daily_tally")
    assert state["days"] == {"2026-10-31": 3, "2026-10-30": 1}
    first, second = http.session.calls[0][2]["params"], http.session.calls[1][2]["params"]
    assert first["startTimestampUnix"] == DAY_START - 1 and first["endTimestampUnix"] == DAY_START + 86400
    assert second["lastDepositAddress"] == "b" and "lastDepositMemo" not in second
    saved = json.loads(gzip.decompress((tmp_path / "bronze/intents_explorer/daily_tally/dt=2026-11-01/2026-10-31.json.gz").read_bytes()))
    assert saved["swaps"] == 3 and saved["pages"] == 3
    assert len(http.session.calls) == 4


def test_explorer_repeats_recent_days_and_skips_finished_older_ones(tmp_path, monkeypatch):
    intents, ctx, http = _explorer_context(tmp_path, monkeypatch, [[_swap(DAY_START + 1, "a")], [_swap(DAY_START - 86400 * 2 + 1, "b")]])
    monkeypatch.setattr(intents, "EXPLORER_RECENT_DAYS", 1)
    monkeypatch.setattr(intents, "EXPLORER_PAGES_PER_RUN", 2)
    ctx.save_state("intents_explorer__daily_tally", {"days": {"2026-10-31": 5, "2026-10-30": 5}})
    intents.explorer_daily_tally(ctx)
    state = ctx.load_state("intents_explorer__daily_tally")
    assert state["days"] == {"2026-10-31": 1, "2026-10-30": 5, "2026-10-29": 1}


def test_explorer_walks_recent_days_then_one_a_week_then_the_rest():
    from ingest.sources import intents

    order = intents.explorer_walk_order(date(2026, 11, 1))
    assert order[0] == date(2026, 10, 31)
    assert len(order) == len(set(order)) == (date(2026, 11, 1) - intents.EXPLORER_FROM).days
    assert min(order) == intents.EXPLORER_FROM
    full, later = order[:intents.EXPLORER_FULL_DAYS], order[intents.EXPLORER_FULL_DAYS:]
    assert full == sorted(full, reverse=True) and min(full) > max(later)
    weekly = len([d for d in later if d.toordinal() % 7 == 0])
    assert all(d.toordinal() % 7 == 0 for d in later[:weekly])
    assert not any(d.toordinal() % 7 == 0 for d in later[weekly:])
    assert later[0] - later[1] == timedelta(days=7)
    # The weekly days stay the same from night to night, so nothing is walked twice for moving a day.
    assert set(later[:weekly]) <= set(intents.explorer_walk_order(date(2026, 11, 2)))
    assert later[0] in intents.explorer_walk_order(date(2026, 11, 2))[intents.EXPLORER_FULL_DAYS:]


def test_explorer_marks_an_empty_day_done_without_saving_a_file(tmp_path, monkeypatch):
    intents, ctx, http = _explorer_context(tmp_path, monkeypatch, [[]])
    monkeypatch.setattr(intents, "EXPLORER_PAGES_PER_RUN", 1)
    intents.explorer_daily_tally(ctx)
    assert ctx.load_state("intents_explorer__daily_tally")["days"] == {"2026-10-31": 0}
    assert not (tmp_path / "bronze/intents_explorer").exists()


def test_explorer_keeps_a_finished_day_when_a_later_call_fails(tmp_path, monkeypatch):
    intents, ctx, http = _explorer_context(tmp_path, monkeypatch, [[_swap(DAY_START + 1, "a")]])
    http.session.replies.append(FakeResponse(400, b"bad request"))
    intents.explorer_daily_tally(ctx)
    assert ctx.load_state("intents_explorer__daily_tally")["days"] == {"2026-10-31": 1}
    assert ctx.warnings and "2026-10-30" in ctx.warnings[0]


def test_block_heights_are_found_before_the_block_sampler_needs_them():
    from ingest import sources  # noqa: F401
    from ingest.pipeline import select

    names = [f"{d.source}/{d.name}" for d in select("all", None, None)]
    assert names.index("rpc/block_day") < names.index("neardata/receiver_sample")


def test_rpc_sends_the_fastnear_key_when_there_is_one(monkeypatch):
    from ingest.sources import rpc

    http = client([FakeResponse(200, b'{"result": 1}'), FakeResponse(200, b'{"result": 2}')])
    ctx = Context("2026-11-01", http, None)
    monkeypatch.delenv("FASTNEAR_API_KEY", raising=False)
    assert rpc._result(ctx, "https://example.test/rpc", "status", []) == 1
    assert not http.session.calls[0][2].get("headers")
    monkeypatch.setenv("FASTNEAR_API_KEY", "test-value")
    assert rpc._result(ctx, "https://example.test/rpc", "status", []) == 2
    assert http.session.calls[1][2]["headers"] == {"Authorization": "Bearer test-value"}


def _nrr_page(**changes):
    data = {
        "updatedAt": "2026-11-02T12:55:58Z",
        "fundDetails": {"asOfDate": "2026-10-30", "sharesOutstanding": 3220000, "netAssets": 72197954.46,
                        "stakingMetrics": {"grossStakingRewardRate": 0.05, "netStakingRewardRate": 0.033, "currentPercentageOfAssetsStaked": 0.999, "asOfDate": "2026-10-31"}},
        "holdings": {"asOfDate": "2026-10-30", "basket": [{"companyName": "NEAR", "shares": 16830051.85}]},
        "premiumDiscount": {"asOfDate": "2026-10-29", "volume": 326922},
        "navAndMarketPrice": {"chart": {"nav": [[1790712000000, 26.46], [1793304000000, 22.999999999999993]], "marketPrice": [[1790712000000, 26.15], [1793304000000, 23.03]]}},
        "wallets": {"updatedAt": "2026-11-02T12:21:52Z", "walletBalances": [{"address": "a" * 64, "balance": 100.5, "active": True}]},
    }
    data.update(changes)
    doc = {"props": {"pageProps": {"fundData": {"data": data}, "marketing": "not a figure"}}}
    return f'<html><body><h1>Marketing copy</h1><script id="__NEXT_DATA__" type="application/json">{json.dumps(doc)}</script></body></html>'


def test_nrr_page_keeps_the_figures_and_cleans_chart_values():
    from ingest.parsers import nrr_page

    parsed = nrr_page.parse(_nrr_page())
    assert parsed["as_of"] == "2026-10-30" and parsed["shares_outstanding"] == 3220000
    assert parsed["nav_chart"] == [{"day": "2026-09-29", "value": 26.46}, {"day": "2026-10-29", "value": 23.0}]
    assert parsed["wallets"] == [{"address": "a" * 64, "balance": 100.5, "active": True}]


@pytest.mark.parametrize("page", [
    "<html>a redesign without the embedded data</html>",
    _nrr_page(fundDetails={"asOfDate": "2026-10-30"}),
    _nrr_page(holdings={"asOfDate": "2026-10-30", "basket": [{"companyName": "Something else", "shares": 1.0}]}),
    _nrr_page(wallets={"updatedAt": "2026-11-02T12:21:52Z", "walletBalances": []}),
])
def test_nrr_page_fails_loudly_when_it_changes(page):
    from ingest.parsers import nrr_page

    with pytest.raises(ValueError, match="NRR page"):
        nrr_page.parse(page)


def _nrr_context(tmp_path, monkeypatch, replies, snapshot="2026-10-01"):
    from ingest import sources  # noqa: F401
    from ingest.sources import etf

    monkeypatch.setattr("ingest.pipeline.STATE", tmp_path)
    monkeypatch.delenv("FASTNEAR_API_KEY", raising=False)
    http = client(replies)
    http.policies["nrretf.com"] = HostPolicy()
    http.policies["archival-rpc.mainnet.fastnear.com"] = HostPolicy()
    return etf, Context(snapshot, http, BronzeWriter(snapshot, root=tmp_path / "bronze")), http


def test_nrr_figures_save_no_page_and_remember_every_wallet_seen(tmp_path, monkeypatch):
    etf, ctx, _ = _nrr_context(tmp_path, monkeypatch, [FakeResponse(200, _nrr_page().encode())])
    ctx.save_state("nrr_fund__wallets", ["b" * 64])
    etf.nrr_figures(ctx)
    saved = gzip.decompress((tmp_path / "bronze/nrr_fund/figures/dt=2026-10-01/page.json.gz").read_bytes()).decode()
    assert "Marketing copy" not in saved and "not a figure" not in saved
    assert json.loads(saved)["shares_outstanding"] == 3220000
    assert ctx.load_state("nrr_fund__wallets") == ["a" * 64, "b" * 64]


def _pool_reply(*accounts):
    rows = [{"account_id": a, "staked_balance": str(staked), "unstaked_balance": str(unstaked), "can_withdraw": True} for a, staked, unstaked in accounts]
    return FakeResponse(200, json.dumps({"result": {"block_height": 1, "result": list(json.dumps(rows).encode())}}).encode())


def test_nrr_pool_keeps_the_funds_wallets_and_only_a_total_for_others(tmp_path, monkeypatch):
    etf, ctx, http = _nrr_context(tmp_path, monkeypatch, [_pool_reply(("fund.near", 5, 2), ("person.near", 10**30, 3), ("other.near", 7, 0))])
    monkeypatch.setattr(etf, "FIRST_BLOCK_DAY", date(2026, 10, 1))
    ctx.save_state("nrr_fund__wallets", ["fund.near"])
    ctx.save_state("rpc__block_day", {"2026-10-01": 500})
    etf.nrr_pool_daily(ctx)
    saved = json.loads(gzip.decompress((tmp_path / "bronze/rpc/nrr_pool_daily/dt=2026-10-01/from_2026-09-30.json.gz").read_bytes()))
    assert saved == [{"closes_day": "2026-09-30", "height": 500, "delegators": 3, "other_delegators_yocto": str(10**30 + 10),
                      "wallets": [{"account_id": "fund.near", "staked": "5", "unstaked": "2"}]}]
    assert "person.near" not in json.dumps(saved)
    params = json.loads(json.dumps(http.session.calls[0][2]["json"]))["params"]
    assert params["block_id"] == 500 and params["account_id"] == etf.POOL and params["method_name"] == "get_accounts"


def test_nrr_pool_reads_every_page_of_delegators(tmp_path, monkeypatch):
    etf, ctx, http = _nrr_context(tmp_path, monkeypatch, [_pool_reply(("a", 1, 0), ("b", 1, 0)), _pool_reply(("c", 1, 0))])
    monkeypatch.setattr(etf, "FIRST_BLOCK_DAY", date(2026, 10, 1))
    monkeypatch.setattr(etf, "ACCOUNTS_PER_CALL", 2)
    ctx.save_state("nrr_fund__wallets", ["a", "c"])
    ctx.save_state("rpc__block_day", {"2026-10-01": 500})
    etf.nrr_pool_daily(ctx)
    saved = json.loads(gzip.decompress((tmp_path / "bronze/rpc/nrr_pool_daily/dt=2026-10-01/from_2026-09-30.json.gz").read_bytes()))
    assert saved[0]["delegators"] == 3 and [w["account_id"] for w in saved[0]["wallets"]] == ["a", "c"]


def test_nrr_pool_reads_recent_days_again_and_older_days_only_once(tmp_path, monkeypatch):
    etf, ctx, http = _nrr_context(tmp_path, monkeypatch, [_pool_reply(("fund.near", 1, 0)) for _ in range(4)], snapshot="2026-10-10")
    monkeypatch.setattr(etf, "FIRST_BLOCK_DAY", date(2026, 10, 1))
    ctx.save_state("nrr_fund__wallets", ["fund.near"])
    ctx.save_state("rpc__block_day", {d: 100 + i for i, d in enumerate(["2026-10-01", "2026-10-02", "2026-10-08", "2026-10-09", "2026-10-10"])})
    ctx.save_state("rpc__nrr_pool_daily", ["2026-10-01", "2026-10-08", "2026-10-09"] + [f"2026-10-0{d}" for d in range(3, 8)])
    etf.nrr_pool_daily(ctx)
    read = [json.loads(json.dumps(call[2]["json"]))["params"]["block_id"] for call in http.session.calls]
    assert read == [101, 102, 103, 104]  # 10-02 was never read; 10-08 to 10-10 are recent; 10-01 and 10-03 to 10-07 are finished
    assert ctx.warnings == []
    assert "2026-10-02" in ctx.load_state("rpc__nrr_pool_daily")


def test_nrr_pool_warns_when_a_days_height_is_unknown(tmp_path, monkeypatch):
    etf, ctx, http = _nrr_context(tmp_path, monkeypatch, [])
    monkeypatch.setattr(etf, "FIRST_BLOCK_DAY", date(2026, 10, 1))
    ctx.save_state("nrr_fund__wallets", ["fund.near"])
    ctx.save_state("rpc__block_day", {})
    etf.nrr_pool_daily(ctx)
    assert ctx.warnings == ["2026-10-01: no block height known yet"]
    assert ctx.load_state("rpc__nrr_pool_daily") is None


def test_nrr_pool_skips_until_there_is_a_wallet_list(tmp_path, monkeypatch):
    etf, ctx, _ = _nrr_context(tmp_path, monkeypatch, [])
    with pytest.raises(Skip):
        etf.nrr_pool_daily(ctx)


def test_block_heights_and_the_wallet_list_come_before_the_pool_read():
    from ingest import sources  # noqa: F401
    from ingest.pipeline import select

    names = [f"{d.source}/{d.name}" for d in select("all", None, None)]
    assert names.index("rpc/block_day") < names.index("rpc/nrr_pool_daily")
    assert names.index("nrr_fund/figures") < names.index("rpc/nrr_pool_daily")


def _borsh_text(value):
    return len(value.encode()).to_bytes(4, "little") + value.encode()


def _lockup_state(amount=10**30, withdrawn=0, duration=0, release=None, timestamp=None, poll=None, vesting=b"\x00", staking=None, foundation="foundation.near"):
    """A lockup contract's state as the chain stores it. Field order follows near/core-contracts lockup/src/lib.rs."""
    state = _borsh_text("person.near") + amount.to_bytes(16, "little") + withdrawn.to_bytes(16, "little") + duration.to_bytes(8, "little")
    state += b"\x01" + release.to_bytes(8, "little") if release is not None else b"\x00"
    state += b"\x01" + timestamp.to_bytes(8, "little") if timestamp is not None else b"\x00"
    state += b"\x01" + _borsh_text(poll) if poll else b"\x00" + (1602614338293769340).to_bytes(8, "little")
    state += vesting + _borsh_text("lockup-whitelist.near")
    state += b"\x01" + _borsh_text(staking) + b"\x00" + (5).to_bytes(16, "little") if staking else b"\x00"
    state += b"\x01" + _borsh_text(foundation) if foundation else b"\x00"
    return state


def test_lockup_state_decodes_each_kind_of_vesting_and_returns_no_names():
    from ingest.sources.lockups import parse_state

    schedule = b"\x02" + (1).to_bytes(8, "little") + (2).to_bytes(8, "little") + (3).to_bytes(8, "little")
    hashed = b"\x01" + (2).to_bytes(4, "little") + b"ab"
    terminating = b"\x03" + (7).to_bytes(16, "little") + b"\x04"
    assert parse_state(_lockup_state(vesting=schedule))["vesting_end_ns"] == 3
    assert parse_state(_lockup_state(vesting=hashed))["vesting_kind"] == "hash"
    assert parse_state(_lockup_state(vesting=terminating))["unvested"] == 7
    fields = parse_state(_lockup_state(release=9, timestamp=8, poll="transfer-vote.near", staking="pool.near", withdrawn=4))
    assert (fields["release_duration_ns"], fields["lockup_timestamp_ns"], fields["withdrawn"], fields["transfers_enabled"]) == (9, 8, 4, False)
    assert not {"person.near", "pool.near", "foundation.near", "transfer-vote.near"} & {str(v) for v in fields.values()}


@pytest.mark.parametrize("raw", [b"", b"\x01\x00\x00", _lockup_state() + b"x", _lockup_state()[:-3]])
def test_lockup_state_refuses_what_is_not_a_lockup(raw):
    from ingest.sources.lockups import parse_state

    with pytest.raises(ValueError):
        parse_state(raw)


def test_factory_lockups_are_numbered_by_funding_and_leave_the_rest_out():
    from ingest.sources.lockups import factory_lockups

    def transfer(other, height, asset="native:near", amount="-5"):
        return {"other_account_id": other, "asset_id": asset, "block_height": str(height), "block_timestamp": str(height * 1000), "amount": amount}

    found = factory_lockups([transfer("b.lockup.near", 20), transfer("a.lockup.near", 30), transfer("b.lockup.near", 10), transfer("near", 5),
                             transfer("c.lockup.near", 1, asset="nep141:x"), transfer(None, 6), transfer("d.lockup.near", 30),
                             transfer("e.lockup.near", 2, amount="5"), transfer("a.lockup.near", 30)])
    assert found == [("b.lockup.near", 10, 10000), ("b.lockup.near", 20, 20000), ("a.lockup.near", 30, 30000), ("d.lockup.near", 30, 30000)]


def test_daily_balances_keep_each_days_last_and_leave_out_the_day_under_way():
    from ingest.sources.lockups import daily_balances

    def transfer(day_seconds, height, balance, asset="native:near"):
        return {"asset_id": asset, "block_height": str(height), "block_timestamp": str(day_seconds * 10**9), "end_of_block_balance": balance}

    day_one, day_two = 1793404800, 1793491200  # 2026-10-31 and 2026-11-01, UTC
    rows = daily_balances("lockup.near", [transfer(day_one, 2, "20"), transfer(day_one, 1, "10"), transfer(day_one, 3, "1", asset="nep141:x"), transfer(day_two, 4, "40")], "2026-11-01")
    assert rows == [{"account_id": "lockup.near", "date_day": "2026-10-31", "balance_yocto": "20"}]


class _FakeChain:
    """Answers the fetcher's calls by what they ask for, so a test need not care about their order."""

    def __init__(self, lockups, gone=(), last_transfers=None, contributors=()):
        self.lockups, self.gone, self.last_transfers, self.contributors = lockups, set(gone), last_transfers or {}, list(contributors)
        self.headers, self.calls = {}, []
        self.factory = [{"other_account_id": a, "asset_id": "native:near", "block_height": str(h), "block_timestamp": str(h * 10**9), "end_of_block_balance": "7", "amount": "-5"}
                        for a, (h, _) in lockups.items()]

    def _reply(self, payload):
        return FakeResponse(200, json.dumps(payload).encode())

    def request(self, method, url, **kw):
        body = kw.get("json") or {}
        self.calls.append(body)
        if "transfers" in url:
            account = body["account_id"]
            if account == "lockup.near":
                return self._reply({"transfers": self.factory, "resume_token": None})
            if account == "contributors.near":
                return self._reply({"transfers": self.contributors, "resume_token": None})
            if not body.get("desc") and account in getattr(self, "account_transfers", {}):
                return self._reply({"transfers": self.account_transfers[account], "resume_token": None})
            return self._reply({"transfers": self.last_transfers.get(account, [])[:1], "resume_token": None})
        params = body["params"]
        if body["method"] == "block":
            height = params.get("block_id", 1000)
            return self._reply({"result": {"header": {"height": height, "timestamp": height * 10}}})
        kind = params["request_type"]
        if kind == "view_account":
            return self._reply({"result": {"amount": "99", "code_hash": "code"}})
        if kind == "call_function":
            answer = "5" if params["method_name"] == "get_locked_amount" else True
            return self._reply({"result": {"block_height": 1, "result": list(json.dumps(answer).encode())}})
        account, height = params["account_id"], params.get("block_id")
        if account in self.gone and height is None:
            return self._reply({"result": {"error": f"account {account} does not exist while viewing"}})
        created, state = self.lockups[account]
        if height is not None and height < created:
            return self._reply({"result": {"error": f"account {account} does not exist while viewing"}})
        state = state(height or 1000) if callable(state) else state
        return self._reply({"result": {"values": [{"key": "U1RBVEU=", "value": base64.b64encode(state).decode()}], "block_height": height or 1000}})


def _lockups_run(tmp_path, monkeypatch, chain, snapshot="2026-11-05"):
    from ingest.sources import lockups

    bronze = tmp_path / "bronze"
    monkeypatch.setattr("ingest.pipeline.STATE", tmp_path)
    monkeypatch.setattr(lockups, "BRONZE", bronze)
    monkeypatch.delenv("FASTNEAR_API_KEY", raising=False)
    http = HttpClient(policies={"archival-rpc.mainnet.fastnear.com": HostPolicy(), "free.rpc.fastnear.com": HostPolicy(), "transfers.main.fastnear.com": HostPolicy()}, log=lambda m: None)
    http.session = chain
    ctx = Context(snapshot, http, BronzeWriter(snapshot, root=bronze))
    lockups.lockups(ctx)
    ctx.bronze.flush()
    return lockups, ctx, bronze


def _saved(bronze, key, snapshot="2026-11-05"):
    return json.loads(gzip.decompress((bronze / f"rpc/lockups/dt={snapshot}/{key}.json.gz").read_bytes()))


def test_lockups_store_schedules_by_number_and_no_account_name(tmp_path, monkeypatch):
    chain = _FakeChain({"aaa.lockup.near": (100, _lockup_state(release=10**18, poll="transfer-vote.near")), "bbb.lockup.near": (200, _lockup_state())},
                       gone=["bbb.lockup.near"], last_transfers={"bbb.lockup.near": [{"block_height": "500", "block_timestamp": "900"}]})
    _, _, bronze = _lockups_run(tmp_path, monkeypatch, chain)
    rows = _saved(bronze, "schedules")
    assert [(r["lockup_no"], r["status"]) for r in rows] == [(1, "live"), (2, "deleted")]
    assert rows[0]["lockup_amount"] == str(10**30) and rows[0]["transfers_enabled"] is False and rows[1]["gone_ns"] == "900"
    everything = "".join(p.read_bytes().decode("latin1") + gzip.decompress(p.read_bytes()).decode() for p in (bronze / "rpc/lockups/dt=2026-11-05").glob("*.gz"))
    everything += (bronze / "_manifest/dt=2026-11-05.jsonl").read_text()
    for name in ("aaa.lockup.near", "bbb.lockup.near", "person.near", "lockup-whitelist.near"):
        assert name not in everything


def test_lockups_a_later_run_reads_only_what_can_still_change_and_saves_only_what_did(tmp_path, monkeypatch):
    far_future = 2 * 10**18
    state = {"finished.lockup.near": (100, _lockup_state()), "running.lockup.near": (200, _lockup_state(timestamp=far_future))}
    _lockups_run(tmp_path, monkeypatch, _FakeChain(state))
    later = _FakeChain({**state, "new.lockup.near": (300, _lockup_state())})
    _, _, bronze = _lockups_run(tmp_path, monkeypatch, later, snapshot="2026-11-06")
    assert [r["lockup_no"] for r in _saved(bronze, "schedules", "2026-11-06")] == [3]
    read = [c["params"]["account_id"] for c in later.calls if c.get("method") == "query" and c["params"]["request_type"] == "view_state"]
    assert "finished.lockup.near" not in read and "running.lockup.near" in read and "new.lockup.near" in read


def _termination_chain(start=500, end=800):
    vesting = b"\x02" + (1).to_bytes(8, "little") + (2).to_bytes(8, "little") + (3 * 10**18).to_bytes(8, "little")
    terminating = b"\x03" + (7).to_bytes(16, "little") + b"\x04"

    def state(height):
        if height < start:
            return _lockup_state(vesting=vesting)
        return _lockup_state(vesting=terminating) if height < end else _lockup_state(withdrawn=7)

    return _FakeChain({"staff.lockup.near": (100, state)})


def test_lockups_a_termination_is_saved_with_when_it_started_and_finished(tmp_path, monkeypatch):
    _, _, bronze = _lockups_run(tmp_path, monkeypatch, _termination_chain())
    row = _saved(bronze, "schedules")[0]
    assert (row["vesting_kind"], row["last_vesting_kind"], row["last_withdrawn"], row["terminating_unvested"]) == ("schedule", "none", "7", "7")
    assert (row["changed_ns"], row["finished_ns"]) == ("5000", "8000")


def test_lockups_a_termination_still_open_needs_no_end_until_a_later_run_sees_it(tmp_path, monkeypatch):
    _, _, bronze = _lockups_run(tmp_path, monkeypatch, _termination_chain(end=5000))
    row = _saved(bronze, "schedules")[0]
    assert (row["last_vesting_kind"], row["last_unvested"], row["changed_ns"], row["finished_ns"]) == ("terminating", "7", "5000", "5000")
    later = _termination_chain(end=1000)
    # The tip now shows it finished, and the search looks only above the height of the earlier read.
    row_before = dict(row)
    _, _, bronze = _lockups_run(tmp_path, monkeypatch, later, snapshot="2026-11-06")
    row = _saved(bronze, "schedules", "2026-11-06")[0]
    assert (row["last_vesting_kind"], row["last_withdrawn"], row["terminating_unvested"]) == ("none", "7", "7")
    assert row["changed_ns"] == row_before["changed_ns"] and row["finished_ns"] == "10000"


def test_lockups_a_rerun_on_one_day_keeps_that_days_earlier_rows(tmp_path, monkeypatch):
    state = {"first.lockup.near": (100, _lockup_state())}
    _lockups_run(tmp_path, monkeypatch, _FakeChain(state))
    _, _, bronze = _lockups_run(tmp_path, monkeypatch, _FakeChain({**state, "second.lockup.near": (200, _lockup_state())}))
    assert [r["lockup_no"] for r in _saved(bronze, "schedules")] == [1, 2]


def test_lockups_refuse_to_guess_when_the_factorys_order_changes(tmp_path, monkeypatch):
    _lockups_run(tmp_path, monkeypatch, _FakeChain({"first.lockup.near": (100, _lockup_state())}))
    from ingest.sources import lockups

    moved = _FakeChain({"other.lockup.near": (50, _lockup_state()), "first.lockup.near": (100, _lockup_state())})
    _, ctx, bronze = _lockups_run(tmp_path, monkeypatch, moved, snapshot="2026-11-06")
    assert any("order no longer matches" in w for w in ctx.warnings)
    assert lockups.known_rows()[1]["created_height"] == 100


def test_lockups_a_name_used_twice_is_two_lockups_and_the_tip_describes_only_the_second(tmp_path, monkeypatch):
    first, second = _lockup_state(amount=9 * 10**30), _lockup_state(amount=2 * 10**30)
    chain = _FakeChain({"owner.lockup.near": (100, lambda height: first if height < 500 else second)})
    chain.factory.append({**chain.factory[0], "block_height": "500", "block_timestamp": str(500 * 10**9)})
    chain.last_transfers = {"owner.lockup.near": []}
    chain.account_transfers = {"owner.lockup.near": [{"block_height": "300", "block_timestamp": "3000"}, {"block_height": "500", "block_timestamp": "5000"}]}
    _, _, bronze = _lockups_run(tmp_path, monkeypatch, chain)
    rows = _saved(bronze, "schedules")
    assert [(r["lockup_no"], r["lockup_amount"], r["status"], r["gone_ns"]) for r in rows] == [(1, str(9 * 10**30), "deleted", "3000"), (2, str(2 * 10**30), "live", None)]


def test_lockups_run_after_block_heights_are_known():
    from ingest import sources  # noqa: F401
    from ingest.pipeline import REGISTRY

    names = [f"{d.source}/{d.name}" for d in REGISTRY]
    assert names.index("rpc/block_day") < names.index("rpc/lockups")
