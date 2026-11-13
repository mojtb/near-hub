"""Unit tests for the ingest layer. They need no network: HTTP calls go to a stub session."""
from __future__ import annotations

import base64
import gzip
import hashlib
import itertools
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from ingest.bronze import BronzeWriter, safe_key
from ingest.http import BudgetExceeded, HostPolicy, HttpClient, HttpError
from ingest.parsers import revenue_page
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


def test_bronze_parallel_writer_does_not_put_an_old_line_over_a_newer_one(tmp_path):
    manifest = tmp_path / "_manifest" / "dt=2026-11-01.jsonl"
    first = BronzeWriter("2026-11-01", root=tmp_path)
    first.save("s", "d", "again", b"old", url="u")
    first.flush()
    slow = BronzeWriter("2026-11-01", root=tmp_path)  # starts while the old line is the one on disk
    fast = BronzeWriter("2026-11-01", root=tmp_path)
    fast.save("s", "d", "again", b"new", url="u")
    fast.flush()
    slow.save("s", "d", "other", b"x", url="u")
    slow.flush()
    lines = {e["key"]: e for e in map(json.loads, manifest.read_text().splitlines())}
    assert set(lines) == {"again", "other"}
    assert lines["again"]["sha256"] == hashlib.sha256(b"new").hexdigest()
    assert gzip.decompress((tmp_path / "s/d/dt=2026-11-01/again.json.gz").read_bytes()) == b"new"


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
    env.write_text("# comment\nNEAR_HUB_TEST_A=hello   # inline comment\nNEAR_HUB_TEST_B=\n")
    monkeypatch.delenv("NEAR_HUB_TEST_A", raising=False)
    monkeypatch.delenv("NEAR_HUB_TEST_B", raising=False)
    load_dotenv(env)
    assert secret("NEAR_HUB_TEST_A") == "hello"
    assert secret("NEAR_HUB_TEST_B") is None


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


def test_explorer_tally_reads_grouped_and_decimal_comma_amounts():
    from ingest.sources import intents

    assert intents._usd("550.0350") == 550.035 and intents._usd(None) == 0 and intents._usd("") == 0 and intents._usd(12.5) == 12.5
    assert intents._usd("18,505.12") == 18505.12 and intents._usd("1,234,567.5") == 1234567.5 and intents._usd("1,234,567") == 1234567
    assert intents._usd("544,8666") == 544.8666 and intents._usd("22,1775") == 22.1775 and intents._usd("0,5") == 0.5
    rows = [_swap(1, "a", amount=2000.0), _swap(2, "b", amount=500.0)]
    rows[0]["amountInUsd"], rows[0]["amountOutUsd"] = "18,505.12", "544,8666"
    tally = intents.tally_day(date(2026, 10, 31), rows, 1, set())
    channel = next(c for c in tally["channels"] if c["status"] == "SUCCESS")
    assert channel["amount_in_usd"] == pytest.approx(19005.12)
    assert channel["amount_out_usd"] == round(544.8666 + float(rows[1]["amountOutUsd"]), 2)  # tallies are kept to the cent
    for unreadable in ("18,505", "12,34,567", "1.234,56", "18,50.5", "abc"):
        rows[0]["amountInUsd"] = unreadable
        with pytest.raises(ValueError):
            intents.tally_day(date(2026, 10, 31), rows, 1, set())


def test_explorer_leaves_an_unreadable_day_for_later_and_walks_on(tmp_path, monkeypatch):
    previous = DAY_START - 86400
    bad = _swap(DAY_START + 9, "a")
    bad["amountInUsd"] = "18,505"
    intents, ctx, http = _explorer_context(tmp_path, monkeypatch, [[bad], [_swap(previous + 5, "b")]])
    monkeypatch.setattr(intents, "EXPLORER_PAGES_PER_RUN", 2)
    intents.explorer_daily_tally(ctx)
    assert ctx.load_state("intents_explorer__daily_tally")["days"] == {"2026-10-30": 1}
    assert len(ctx.warnings) == 1 and "2026-10-31" in ctx.warnings[0] and "'18,505'" in ctx.warnings[0]
    saved = tmp_path / "bronze/intents_explorer/daily_tally/dt=2026-11-01"
    assert [p.name for p in saved.iterdir()] == ["2026-10-30.json.gz"]


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


def test_nrr_page_keeps_the_current_day_extras_and_survives_without_them():
    # Read on 2026-11-10: a 0.25% discount, 18 days at a premium and 11 at a discount in 2026, a 0.55% median spread.
    from ingest.parsers import nrr_page

    chart = {"nav": [[1790712000000, 26.46]], "marketPrice": [[1790712000000, 26.15]]}
    page = _nrr_page(
        premiumDiscount={"asOfDate": "2026-11-06", "volume": 92179, "premiumDiscount": -0.0025, "daysTradedAtNav": {"y2026": 0},
                         "daysTradedAtPremium": {"q4y2026": 18, "y2026": 18}, "daysTradedAtDiscount": {"q4y2026": 9, "y2026": 11}},
        navAndMarketPrice={"chart": chart, "thirtyDayMedianBidAskSpread": 0.0054564533, "asOfDateMedianBidAskSpread": "2026-11-06"})
    parsed = nrr_page.parse(page)
    assert parsed["premium_discount_rate"] == -0.0025 and parsed["bid_ask_spread_30d_median_rate"] == 0.0054564533
    assert parsed["days_at_premium"] == {"q4y2026": 18, "y2026": 18} and parsed["days_at_discount"]["y2026"] == 11
    assert parsed["bid_ask_spread_as_of"] == "2026-11-06" and parsed["days_at_nav"] == {"y2026": 0}

    without = nrr_page.parse(_nrr_page())
    assert without["shares_outstanding"] == 3220000
    assert all(without[name] is None for name in nrr_page.EXTRAS)


def test_nrr_page_leaves_out_a_chart_day_not_filled_yet():
    # On 2026-11-09 the page had the NAV for 2026-11-05 but a null market price for it.
    from ingest.parsers import nrr_page

    chart = {"nav": [[1790712000000, 26.46], [1793304000000, 23.0]], "marketPrice": [[1790712000000, 26.15], [1793304000000, None]]}
    parsed = nrr_page.parse(_nrr_page(navAndMarketPrice={"chart": chart}))
    assert parsed["nav_chart"] == [{"day": "2026-09-29", "value": 26.46}, {"day": "2026-10-29", "value": 23.0}]
    assert parsed["market_price_chart"] == [{"day": "2026-09-29", "value": 26.15}]


@pytest.mark.parametrize("page", [
    "<html>a redesign without the embedded data</html>",
    _nrr_page(navAndMarketPrice={"chart": {"nav": [[1790712000000, None]], "marketPrice": [[1790712000000, 26.15]]}}),
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


def _ft_reply(metadata, height=7):
    raw = metadata if isinstance(metadata, bytes) else json.dumps(metadata).encode()
    return FakeResponse(200, json.dumps({"result": {"block_height": height, "logs": [], "result": list(raw)}}).encode())


FT_OK = {"spec": "ft-1.0.0", "name": "Some Token", "symbol": "SOME", "decimals": 18, "icon": "data:image/png;base64,AAAA", "reference": None}
FT_NO_METHOD = FakeResponse(200, json.dumps({"result": {"block_height": 7, "logs": [], "error": "wasm execution failed with error: MethodResolveError(MethodNotFound)"}}).encode())
FT_DELETED = FakeResponse(200, json.dumps({"error": {"name": "HANDLER_ERROR", "cause": {"name": "UNKNOWN_ACCOUNT", "info": {"block_height": 9}}}}).encode())
FT_NODE_TROUBLE = FakeResponse(200, json.dumps({"error": {"name": "HANDLER_ERROR", "cause": {"name": "NO_SYNCED_BLOCKS"}}}).encode())


def _ft_context(tmp_path, monkeypatch, replies, holdings=None, top_holders=None, snapshot="2026-11-06"):
    """Bronze holds one account per {token: balance} in `holdings`, and one top-holder file per {token: holders} in `top_holders`."""
    from ingest import sources  # noqa: F401
    from ingest.sources import rpc

    bronze = tmp_path / "bronze"
    monkeypatch.setattr("ingest.pipeline.STATE", tmp_path / "state")
    monkeypatch.setattr(rpc, "BRONZE", bronze)
    monkeypatch.delenv("FASTNEAR_API_KEY", raising=False)
    for i, tokens in enumerate(holdings or []):
        path = bronze / f"fastnear/account_full/dt=2026-11-05/account{i}.json.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps({"account_id": f"account{i}", "tokens": [{"contract_id": t, "balance": b} for t, b in tokens.items()]}).encode()))
    for token, holders in (top_holders or {}).items():
        path = bronze / f"fastnear/ft_top_holders/dt=2026-11-05/{token}.json.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps({"token_id": token, "accounts": [{"account_id": f"h{n}", "balance": "1"} for n in range(holders)]}).encode()))
    http = client(replies)
    http.policies[rpc.RPC.split("/")[2]] = HostPolicy()
    return rpc, Context(snapshot, http, BronzeWriter(snapshot, root=bronze)), http


def _ft_saved(tmp_path, first_token, snapshot="2026-11-06"):
    return json.loads(gzip.decompress((tmp_path / f"bronze/rpc/ft_metadata/dt={snapshot}/from_{first_token}.json.gz").read_bytes()))


def _ft_read_order(http):
    return [call[2]["json"]["params"]["account_id"] for call in http.session.calls]


def test_ft_metadata_reads_a_token_once_and_keeps_the_answer(tmp_path, monkeypatch):
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [_ft_reply(FT_OK)], holdings=[{"a.near": "5"}])
    rpc.ft_metadata(ctx)
    assert _ft_saved(tmp_path, "a.near") == [{"token_id": "a.near", "block_height": 7, "spec": "ft-1.0.0", "name": "Some Token", "symbol": "SOME", "decimals": 18}]
    assert ctx.load_state("rpc__ft_metadata")["answers"] == {"a.near": {"symbol": "SOME", "decimals": 18}}
    params = http.session.calls[0][2]["json"]["params"]
    assert params["method_name"] == "ft_metadata" and params["finality"] == "final"
    rpc.ft_metadata(ctx)
    assert len(http.session.calls) == 1 and ctx.warnings == []


def test_ft_metadata_reads_the_tokens_with_most_rows_first_and_stops_at_the_cap(tmp_path, monkeypatch):
    holdings = [{"lone.near": "1", "shared.near": "2", "empty.near": "0", "blank.near": "", "gone.near": None}, {"shared.near": "3"}]
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [_ft_reply(FT_OK) for _ in range(3)], holdings=holdings, top_holders={"top.near": 100})
    monkeypatch.setattr(rpc, "FT_METADATA_CALLS_PER_RUN", 2)
    rpc.ft_metadata(ctx)
    assert _ft_read_order(http) == ["top.near", "shared.near"]
    rpc.ft_metadata(ctx)
    assert _ft_read_order(http) == ["top.near", "shared.near", "lone.near"]  # no call for a token with no balance
    assert len(_ft_saved(tmp_path, "top.near")) == 2 and len(_ft_saved(tmp_path, "lone.near")) == 1  # two runs on one day keep both files


def test_ft_metadata_never_guesses_and_keeps_only_the_fields_it_trusts(tmp_path, monkeypatch):
    replies = {"zero.near": _ft_reply({**FT_OK, "decimals": 0}), "true.near": _ft_reply({**FT_OK, "decimals": True}), "text.near": _ft_reply({**FT_OK, "decimals": "18"}),
               "huge.near": _ft_reply({**FT_OK, "decimals": 300}), "none.near": _ft_reply({"symbol": "NONE"}), "list.near": _ft_reply([1, 2]),
               "bytes.near": _ft_reply(b"\xff not json"), "blank.near": _ft_reply(b""), "deep.near": _ft_reply(b"[" * 200000), "method.near": FT_NO_METHOD, "deleted.near": FT_DELETED,
               "messy.near": _ft_reply({**FT_OK, "symbol": "A\u0000B\n‮ C ", "name": "x" * 500, "spec": 5})}
    tokens = sorted(replies)
    rpc, ctx, _ = _ft_context(tmp_path, monkeypatch, [replies[t] for t in tokens], holdings=[{t: "1" for t in tokens}])
    rpc.ft_metadata(ctx)
    rows = {r["token_id"]: r for r in _ft_saved(tmp_path, tokens[0])}
    assert rows["zero.near"]["decimals"] == 0
    for token in ("true.near", "text.near", "huge.near", "none.near"):
        assert rows[token]["error"] == "BAD_DECIMALS" and "decimals" not in rows[token]
    assert rows["none.near"]["symbol"] == "NONE"
    for token in ("list.near", "bytes.near", "blank.near", "deep.near"):
        assert rows[token]["error"] == "NOT_METADATA"
    assert rows["method.near"] == {"token_id": "method.near", "block_height": 7, "error": "CONTRACT_EXECUTION_ERROR"}
    assert rows["deleted.near"] == {"token_id": "deleted.near", "block_height": 9, "error": "UNKNOWN_ACCOUNT"}
    assert rows["messy.near"]["symbol"] == "AB C" and len(rows["messy.near"]["name"]) == 128 and rows["messy.near"]["spec"] is None
    assert ctx.warnings == []
    answers = ctx.load_state("rpc__ft_metadata")["answers"]
    assert answers["zero.near"]["decimals"] == 0 and answers["deleted.near"] == {"error": "UNKNOWN_ACCOUNT"} and set(answers) == set(tokens)


def test_ft_metadata_asks_again_when_the_node_had_no_answer(tmp_path, monkeypatch):
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [FT_NODE_TROUBLE, FakeResponse(200, b"<html>not json</html>"), _ft_reply(FT_OK)],
                                 holdings=[{"a.near": "1", "b.near": "1", "c.near": "1"}])
    rpc.ft_metadata(ctx)
    assert _ft_read_order(http) == ["a.near", "b.near", "c.near"]
    state = ctx.load_state("rpc__ft_metadata")
    assert set(state["answers"]) == {"c.near"} and state["failures"] == {"a.near": 1, "b.near": 1}
    assert len(ctx.warnings) == 2 and "NO_SYNCED_BLOCKS" in ctx.warnings[0]
    http.session.replies.extend([_ft_reply(FT_OK), _ft_reply(FT_OK)])
    rpc.ft_metadata(ctx)
    state = ctx.load_state("rpc__ft_metadata")
    assert set(state["answers"]) == {"a.near", "b.near", "c.near"} and state["failures"] == {}


@pytest.mark.parametrize("reply", [b'{"error": "rate limited"}', b"[1, 2]", b'{"result": {"block_height": 7}}', b'{"result": 5}', b"{}"])
def test_ft_metadata_treats_any_other_reply_as_no_answer(tmp_path, monkeypatch, reply):
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [FakeResponse(200, reply)], holdings=[{"a.near": "1"}])
    rpc.ft_metadata(ctx)
    state = ctx.load_state("rpc__ft_metadata")
    assert state["answers"] == {} and state["failures"] == {"a.near": 1} and len(ctx.warnings) == 1


def test_ft_metadata_stops_for_the_night_when_the_node_keeps_failing(tmp_path, monkeypatch):
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [_ft_reply(FT_OK), FakeResponse(403, b"no"), FakeResponse(403, b"no"), FakeResponse(403, b"no"), _ft_reply(FT_OK)],
                                 holdings=[{f"{c}.near": "1" for c in "abcde"}])
    rpc.ft_metadata(ctx)
    assert _ft_read_order(http) == ["a.near", "b.near", "c.near", "d.near"]  # e.near was never asked
    assert set(ctx.load_state("rpc__ft_metadata")["answers"]) == {"a.near"}  # the answer before the failures is saved
    assert _ft_saved(tmp_path, "a.near")[0]["decimals"] == 18
    assert "stopped early" in ctx.warnings[-1]


def test_ft_metadata_stops_at_once_after_a_call_that_used_every_retry(tmp_path, monkeypatch):
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [FakeResponse(503) for _ in range(6)], holdings=[{"a.near": "1", "b.near": "1"}])
    rpc.ft_metadata(ctx)
    assert _ft_read_order(http) == ["a.near"] * 6
    assert "stopped early" in ctx.warnings[-1]


def test_ft_metadata_stops_when_its_time_is_up(tmp_path, monkeypatch):
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [_ft_reply(FT_OK)], holdings=[{"a.near": "1", "b.near": "1"}])
    clock = itertools.count(step=rpc.FT_METADATA_MINUTES_PER_RUN * 60)  # each look at the clock moves it on by the whole budget
    monkeypatch.setattr(rpc.time, "monotonic", lambda: next(clock))
    rpc.ft_metadata(ctx)
    assert _ft_read_order(http) == ["a.near"]
    assert "stopped after" in ctx.warnings[-1]
    assert set(ctx.load_state("rpc__ft_metadata")["answers"]) == {"a.near"}


def test_ft_metadata_cannot_be_held_up_by_tokens_that_keep_failing(tmp_path, monkeypatch):
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [_ft_reply(FT_OK)], holdings=[{"a.near": "1", "b.near": "1"}])
    monkeypatch.setattr(rpc, "FT_METADATA_CALLS_PER_RUN", 1)
    ctx.save_state("rpc__ft_metadata", {"answers": {}, "failures": {"a.near": 2}})
    rpc.ft_metadata(ctx)
    assert _ft_read_order(http) == ["b.near"]


def test_ft_metadata_reads_again_an_answer_whose_bronze_file_is_gone(tmp_path, monkeypatch):
    # The nightly job drops its bronze dated up to main's pin, while its state file stays. The token must not stay unconverted for good.
    rpc, ctx, http = _ft_context(tmp_path, monkeypatch, [_ft_reply(FT_OK), _ft_reply(FT_OK, height=8)], holdings=[{"a.near": "1"}], snapshot="2026-11-05")
    rpc.ft_metadata(ctx)
    (tmp_path / "bronze/rpc/ft_metadata/dt=2026-11-05/from_a.near.json.gz").unlink()
    later = Context("2026-11-06", http, BronzeWriter("2026-11-06", root=tmp_path / "bronze"))
    rpc.ft_metadata(later)
    assert len(http.session.calls) == 2 and _ft_saved(tmp_path, "a.near")[0]["block_height"] == 8


def test_holdings_and_top_holders_are_fetched_before_token_metadata():
    from ingest import sources  # noqa: F401
    from ingest.pipeline import select

    names = [f"{d.source}/{d.name}" for d in select("all", None, None)]
    assert names.index("fastnear/account_full") < names.index("rpc/ft_metadata")
    assert names.index("fastnear/ft_top_holders") < names.index("rpc/ft_metadata")


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


def test_commits_by_week_cuts_weeks_on_sunday_and_counts_each_author_once():
    from datetime import date

    from ingest.sources.ecosystem import commits_by_week, week_start

    assert week_start(date(2026, 11, 5)) == date(2026, 11, 1)  # a Thursday falls in the week of Sunday 1 November
    assert week_start(date(2026, 11, 1)) == date(2026, 11, 1)  # a Sunday starts its own week
    assert week_start(date(2026, 10, 31)) == date(2026, 10, 25)
    commit = lambda when, login: {"author": {"login": login} if login else None,
                                  "commit": {"committer": {"date": when}, "author": {"email": "x@y", "name": "x"}}}
    commits = [
        commit("2026-10-25T00:00:01Z", "a"), commit("2026-10-31T23:59:59Z", "a"), commit("2026-10-31T12:00:00Z", "b"),
        commit("2026-11-01T00:00:00Z", "a"),  # the next week
        commit("2026-10-18T10:00:00Z", None),  # before the window: dropped
    ]
    weeks = commits_by_week(commits, date(2026, 10, 25), 2)
    assert [w["week"] for w in weeks] == [1792886400, 1793491200]  # 2026-10-25 and 2026-11-01, 00:00 UTC
    assert [(w["total"], w["authors"]) for w in weeks] == [(3, 2), (1, 1)]


def _validators_context(tmp_path, monkeypatch, replies, current=None, block_days=None, snapshot="2026-11-10"):
    """Bronze holds one nightly validators read per {day: (epoch_height, epoch_start_height)} and one block per {day: epoch_id}."""
    from ingest import sources  # noqa: F401
    from ingest.sources import rpc

    bronze = tmp_path / "bronze"
    monkeypatch.setattr("ingest.pipeline.STATE", tmp_path / "state")
    monkeypatch.setattr(rpc, "BRONZE", bronze)
    monkeypatch.delenv("FASTNEAR_API_KEY", raising=False)
    for day, (height, start) in (current or {}).items():
        path = bronze / f"rpc/validators_current/dt={day}/latest.json.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps({"epoch_height": height, "epoch_start_height": start, "validators": []}).encode()))
    for day, epoch_id in (block_days or {}).items():
        path = bronze / f"rpc/block_day/dt={day}/from_{day}.json.gz"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps([{"day": day, "epoch_id": epoch_id}]).encode()))
    http = client(replies)
    http.policies[rpc.ARCHIVAL.split("/")[2]] = HostPolicy()
    return rpc, Context(snapshot, http, BronzeWriter(snapshot, root=bronze)), http


def _epoch_reply(height, blocks_counted):
    validators = [{"account_id": "a.pool", "stake": "1", "num_expected_blocks": blocks_counted, "num_produced_blocks": blocks_counted}]
    return FakeResponse(200, json.dumps({"result": {"epoch_height": height, "epoch_start_height": height * 100, "current_validators": validators}}).encode())


def _block_reply(epoch_id):
    return FakeResponse(200, json.dumps({"result": {"header": {"epoch_id": epoch_id}}}).encode())


def test_validators_epoch_reads_a_nightly_epoch_again_once_a_newer_one_is_seen(tmp_path, monkeypatch):
    current = {"2026-11-08": (10, 1000), "2026-11-09": (13, 1300)}
    rpc, ctx, http = _validators_context(tmp_path, monkeypatch, [_block_reply("E10"), _epoch_reply(10, 43200)], current=current)
    rpc.validators_epoch(ctx)
    ctx.bronze.flush()
    asked = [(call[2]["json"]["method"], call[2]["json"]["params"]) for call in http.session.calls]
    assert asked == [("block", {"block_id": 1000}), ("validators", {"epoch_id": "E10"})]  # epoch 13 may still be running
    saved = json.loads(gzip.decompress((tmp_path / "bronze/rpc/validators_epoch/dt=2026-11-10/epoch_10.json.gz").read_bytes()))
    assert saved["epoch_id"] == "E10" and saved["seen_on_day"] == "2026-11-08" and saved["validators"][0]["num_expected_blocks"] == 43200
    assert ctx.load_state("rpc__validators_epoch")["done"] == ["E10"]
    rpc.validators_epoch(ctx)
    assert len(http.session.calls) == 2  # the whole epoch is on file, so nothing is asked again


def _view_reply(value):
    return FakeResponse(200, json.dumps({"result": {"block_height": 1, "result": list(json.dumps(value).encode())}}).encode())


def _view_error(cause):
    return FakeResponse(200, json.dumps({"error": {"name": "HANDLER_ERROR", "cause": {"name": cause}}}).encode())


def test_view_history_calls_are_all_nightly_views():
    from ingest.sources import rpc

    assert all(call in rpc.VIEW_CALLS for call in rpc.VIEW_HISTORY_CALLS)


def test_contract_views_history_replays_each_day_newest_first_and_keeps_the_chains_own_refusals(tmp_path, monkeypatch):
    days = {"2026-11-08": 800, "2026-11-09": 900}
    replies = [_view_reply("1.5"), _view_error("UNKNOWN_ACCOUNT"),   # 2026-11-09
               _view_reply("1.4"), _view_error("UNKNOWN_ACCOUNT")]   # 2026-11-08
    rpc, ctx, http = _validators_context(tmp_path, monkeypatch, replies)
    path = tmp_path / "bronze/rpc/block_day/dt=2026-11-10/all.json.gz"
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress(json.dumps([{"day": d, "height": h, "epoch_id": "E"} for d, h in days.items()]).encode()))
    monkeypatch.setattr(rpc, "VIEW_HISTORY_CALLS", [("old.near", "ft_price", {}), ("new.near", "ft_price", {})])
    rpc.contract_views_history(ctx)
    asked = [(c[2]["json"]["params"]["block_id"], c[2]["json"]["params"]["account_id"]) for c in http.session.calls]
    assert asked == [(900, "old.near"), (900, "new.near"), (800, "old.near"), (800, "new.near")]
    saved = json.loads(gzip.decompress((tmp_path / "bronze/rpc/contract_views_history/dt=2026-11-10/2026-11-08.json.gz").read_bytes()))
    assert saved["day"] == "2026-11-08" and saved["block_height"] == 800
    assert saved["views"] == [{"contract": "old.near", "method": "ft_price", "args": {}, "result": "1.4"},
                              {"contract": "new.near", "method": "ft_price", "args": {}, "result": None, "error": "UNKNOWN_ACCOUNT"}]
    rpc.contract_views_history(ctx)
    assert len(http.session.calls) == 4  # both days are on file


def test_contract_views_history_stops_asking_about_a_contract_absent_on_two_newer_days(tmp_path, monkeypatch):
    rpc, ctx, http = _validators_context(tmp_path, monkeypatch, [_view_reply("1.3")])
    path = tmp_path / "bronze/rpc/block_day/dt=2026-11-10/all.json.gz"
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress(json.dumps([{"day": d, "height": h, "epoch_id": "E"} for d, h in
                                               {"2026-11-07": 700, "2026-11-08": 800, "2026-11-09": 900}.items()]).encode()))
    for day in ("2026-11-08", "2026-11-09"):
        ctx.bronze.save_json("rpc", "contract_views_history", day, {"day": day, "block_height": 1, "views": [
            {"contract": "old.near", "method": "ft_price", "args": {}, "result": "1.4"},
            {"contract": "new.near", "method": "ft_price", "args": {}, "result": None, "error": "UNKNOWN_ACCOUNT"}]}, url="u")
    monkeypatch.setattr(rpc, "VIEW_HISTORY_CALLS", [("old.near", "ft_price", {}), ("new.near", "ft_price", {})])
    rpc.contract_views_history(ctx)
    assert [c[2]["json"]["params"]["account_id"] for c in http.session.calls] == ["old.near"]
    saved = json.loads(gzip.decompress((tmp_path / "bronze/rpc/contract_views_history/dt=2026-11-10/2026-11-07.json.gz").read_bytes()))
    assert [v["contract"] for v in saved["views"]] == ["old.near"]


def test_contract_views_history_leaves_a_day_unsaved_when_a_node_cannot_answer(tmp_path, monkeypatch):
    rpc, ctx, http = _validators_context(tmp_path, monkeypatch, [_view_error("UNKNOWN_BLOCK"), _view_reply("1.5")])
    path = tmp_path / "bronze/rpc/block_day/dt=2026-11-10/all.json.gz"
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress(json.dumps([{"day": "2026-11-09", "height": 900, "epoch_id": "E"}]).encode()))
    monkeypatch.setattr(rpc, "VIEW_HISTORY_CALLS", [("old.near", "ft_price", {})])
    rpc.contract_views_history(ctx)
    assert not (tmp_path / "bronze/rpc/contract_views_history").exists() and "UNKNOWN_BLOCK" in ctx.warnings[0]
    rpc.contract_views_history(ctx)  # a later run reads the day
    assert (tmp_path / "bronze/rpc/contract_views_history/dt=2026-11-10/2026-11-09.json.gz").exists()


def _refusal():
    return FakeResponse(200, json.dumps({"error": {"name": "HANDLER_ERROR", "cause": {"name": "UNKNOWN_EPOCH"}}}).encode())


def test_validators_epoch_asks_a_refused_epoch_again_on_a_fresh_connection(tmp_path, monkeypatch):
    replies = [_refusal(), _epoch_reply(30, 43200)]
    rpc, ctx, http = _validators_context(tmp_path, monkeypatch, replies, block_days={"2026-11-09": "E30"})
    rpc.validators_epoch(ctx)
    assert ctx.load_state("rpc__validators_epoch")["refused"] == {"E30": 1}
    assert not (tmp_path / "bronze/rpc/validators_epoch").exists()
    rpc.validators_epoch(ctx)  # another node holds it
    state = ctx.load_state("rpc__validators_epoch")
    assert state["done"] == ["E30"] and state["refused"] == {}
    assert (tmp_path / "bronze/rpc/validators_epoch/dt=2026-11-10/epoch_30.json.gz").exists()
    assert [call[2]["headers"]["Connection"] for call in http.session.calls] == ["close", "close"]


def test_validators_epoch_stops_asking_after_the_limit_and_takes_over_the_old_refusals(tmp_path, monkeypatch):
    rpc, ctx, http = _validators_context(tmp_path, monkeypatch, [_refusal()], block_days={"2026-11-09": "E40", "2026-11-08": "E41"})
    monkeypatch.setattr(rpc, "VALIDATOR_ASKS_PER_EPOCH", 2)
    ctx.save_state("rpc__validators_epoch", {"done": ["E41"], "unavailable": ["E40"]})  # as an earlier version saved it
    rpc.validators_epoch(ctx)
    state = ctx.load_state("rpc__validators_epoch")
    assert state["refused"] == {"E40": 2} and "unavailable" not in state
    rpc.validators_epoch(ctx)
    assert len(http.session.calls) == 1  # refused twice, the limit here, so it is left alone


def test_validators_epoch_counts_an_epoch_on_file_as_read_whatever_the_state_says(tmp_path, monkeypatch):
    rpc, ctx, http = _validators_context(tmp_path, monkeypatch, [], block_days={"2026-11-09": "E50"})
    path = tmp_path / "bronze/rpc/validators_epoch/dt=2026-11-05/epoch_50.json.gz"
    path.parent.mkdir(parents=True)
    path.write_bytes(gzip.compress(json.dumps({"epoch_id": "E50", "epoch_height": 50, "validators": []}).encode()))
    ctx.save_state("rpc__validators_epoch", {"done": [], "unavailable": ["E50"]})
    rpc.validators_epoch(ctx)
    assert http.session.calls == []


def test_validators_epoch_keeps_nothing_from_an_epoch_still_in_progress(tmp_path, monkeypatch):
    replies = [_epoch_reply(20, 1297), _epoch_reply(20, 43200)]
    rpc, ctx, http = _validators_context(tmp_path, monkeypatch, replies, block_days={"2026-11-10": "E20"})
    rpc.validators_epoch(ctx)
    ctx.bronze.flush()
    assert not (tmp_path / "bronze/rpc/validators_epoch").exists()
    assert ctx.load_state("rpc__validators_epoch", {"done": []})["done"] == []
    rpc.validators_epoch(ctx)  # a later run finds it finished
    ctx.bronze.flush()
    assert (tmp_path / "bronze/rpc/validators_epoch/dt=2026-11-10/epoch_20.json.gz").exists()
    assert ctx.load_state("rpc__validators_epoch")["done"] == ["E20"]


_SWAP_SERVICES = [
    {"service_id": "near_intents", "llama_dimension": "", "llama_slug": "", "llama_id": "", "llama_data_type": ""},
    {"service_id": "thorchain", "llama_dimension": "dexs", "llama_slug": "thorchain-dex", "llama_id": "412", "llama_data_type": "dailyVolume"},
    {"service_id": "across", "llama_dimension": "bridges", "llama_slug": "across", "llama_id": "1207", "llama_data_type": "dailyOutgoingVolume"},
]


def _swap_services_context(tmp_path, monkeypatch, replies):
    from ingest.sources import defillama

    monkeypatch.setattr(defillama, "read_registry", lambda name: _SWAP_SERVICES)
    http = client(replies)
    return defillama, Context("2026-11-12", http, BronzeWriter("2026-11-12", root=tmp_path / "bronze")), http


def _saved_swap_services(tmp_path):
    folder = tmp_path / "bronze/defillama/swap_service_volume/dt=2026-11-12"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_swap_services_ask_each_service_of_its_own_list_and_leave_near_intents_out(tmp_path, monkeypatch):
    thorchain = b'{"defillamaId": "412", "totalDataChart": [[1794355200, 5]]}'
    across = b'{"defillamaId": "1207", "totalDataChart": [[1794355200, 7]]}'
    defillama, ctx, http = _swap_services_context(tmp_path, monkeypatch, [FakeResponse(200, thorchain), FakeResponse(200, across)])
    defillama.swap_service_volume(ctx)
    assert [(url, kw["params"]["dataType"]) for _, url, kw in http.session.calls] == [
        ("https://api.llama.fi/summary/dexs/thorchain-dex", "dailyVolume"),
        ("https://api.llama.fi/summary/bridges/across", "dailyOutgoingVolume")]
    assert _saved_swap_services(tmp_path) == ["bridges__across.json.gz", "dexs__thorchain-dex.json.gz"]
    saved = tmp_path / "bronze/defillama/swap_service_volume/dt=2026-11-12/bridges__across.json.gz"
    assert gzip.decompress(saved.read_bytes()) == across  # the reply as it arrived
    assert not ctx.warnings


def test_swap_services_refuse_a_reply_that_carries_another_id(tmp_path, monkeypatch):
    regrouped = b'{"defillamaId": "parent#thorchain", "totalDataChart": [[1794355200, 5]]}'
    across = b'{"defillamaId": "1207", "totalDataChart": [[1794355200, 7]]}'
    defillama, ctx, _ = _swap_services_context(tmp_path, monkeypatch, [FakeResponse(200, regrouped), FakeResponse(200, across)])
    defillama.swap_service_volume(ctx)
    assert _saved_swap_services(tmp_path) == ["bridges__across.json.gz"]
    assert len(ctx.warnings) == 1 and "thorchain-dex" in ctx.warnings[0] and "412" in ctx.warnings[0]


def test_swap_services_one_failing_service_does_not_lose_the_rest(tmp_path, monkeypatch):
    across = b'{"defillamaId": "1207", "totalDataChart": [[1794355200, 7]]}'
    defillama, ctx, _ = _swap_services_context(tmp_path, monkeypatch, [FakeResponse(400, b"Dexs for thorchain-dex not found"), FakeResponse(200, across)])
    defillama.swap_service_volume(ctx)
    assert _saved_swap_services(tmp_path) == ["bridges__across.json.gz"]
    assert len(ctx.warnings) == 1 and "HTTP 400" in ctx.warnings[0]


_TOKEN_PRICES = [
    {"symbol": "ZEC", "price_source": "coinmetrics", "source_asset_id": "zec"},
    {"symbol": "WBTC", "price_source": "defillama", "source_asset_id": "coingecko:wrapped-bitcoin"},
    {"symbol": "TLO", "price_source": "defillama", "source_asset_id": "ethereum:0x0f38"},
    {"symbol": "NOSRC", "price_source": "", "source_asset_id": ""},
    {"symbol": "SOL", "price_source": "coinmetrics", "source_asset_id": "sol"},
]


def _token_price_context(tmp_path, monkeypatch, module, replies, snapshot="2026-11-12"):
    monkeypatch.setattr(module, "read_registry", lambda name: _TOKEN_PRICES)
    monkeypatch.setattr("ingest.sources._common.BRONZE", tmp_path / "bronze")  # where has_prior looks for an earlier read
    http = client(replies)
    return Context(snapshot, http, BronzeWriter(snapshot, root=tmp_path / "bronze")), http


def _saved_token_prices(tmp_path, source, snapshot="2026-11-12"):
    folder = tmp_path / f"bronze/{source}/token_price/dt={snapshot}"
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_coinmetrics_token_price_asks_only_its_own_assets_for_the_price_alone(tmp_path, monkeypatch):
    from ingest.sources import market

    zec = b'{"data": [{"asset": "zec", "time": "2026-11-11T00:00:00.000000000Z", "PriceUSD": "963.4"}]}'
    ctx, http = _token_price_context(tmp_path, monkeypatch, market, [FakeResponse(200, zec), FakeResponse(400, b"Value 'sol' is not supported")])
    market.coinmetrics_token_price(ctx)
    asked = [(kw["params"]["assets"], kw["params"]["metrics"], kw["params"]["start_time"]) for _, _, kw in http.session.calls]
    assert asked == [("zec", "PriceUSD", "2024-11-01"), ("sol", "PriceUSD", "2024-11-01")]  # a first read asks for the whole history
    assert all("ignore_unsupported_errors" not in kw["params"] for _, _, kw in http.session.calls)
    assert _saved_token_prices(tmp_path, "coinmetrics") == ["zec.json.gz"]  # one asset failing does not lose the other
    assert gzip.decompress((tmp_path / "bronze/coinmetrics/token_price/dt=2026-11-12/zec.json.gz").read_bytes()) == zec
    assert len(ctx.warnings) == 1 and "sol" in ctx.warnings[0] and "HTTP 400" in ctx.warnings[0]


def test_coinmetrics_token_price_reads_only_the_overlap_once_an_asset_has_a_file(tmp_path, monkeypatch):
    from ingest.sources import market

    BronzeWriter("2026-11-12", root=tmp_path / "bronze").save("coinmetrics", "token_price", "zec", b"{}", url="u")
    ctx, http = _token_price_context(tmp_path, monkeypatch, market, [FakeResponse(200, b'{"data": []}'), FakeResponse(200, b'{"data": []}')], snapshot="2026-11-13")
    market.coinmetrics_token_price(ctx)
    assert [(kw["params"]["assets"], kw["params"]["start_time"]) for _, _, kw in http.session.calls] == [("zec", "2026-10-30"), ("sol", "2024-11-01")]


def _llama_prices(coin, symbol, *points):
    return json.dumps({"coins": {coin: {"symbol": symbol, "confidence": 0.99, "prices": [{"timestamp": t, "price": p} for t, p in points]}}}).encode()


def test_defillama_token_price_asks_each_coin_by_its_own_key_and_keeps_an_empty_window(tmp_path, monkeypatch):
    from ingest.sources import defillama

    wbtc = _llama_prices("coingecko:wrapped-bitcoin", "WBTC", (1794355200, 73660.0))
    tlo = _llama_prices("ethereum:0x0f38", "TLO", (1794355200, 1.0281))
    empty = b'{"coins":{}}'
    ctx, http = _token_price_context(tmp_path, monkeypatch, defillama, [FakeResponse(200, wbtc)] * 3 + [FakeResponse(200, empty), FakeResponse(200, tlo), FakeResponse(200, tlo)])
    defillama.token_price(ctx)
    urls = [url for _, url, _ in http.session.calls]
    assert urls == ["https://coins.llama.fi/chart/coingecko:wrapped-bitcoin"] * 3 + ["https://coins.llama.fi/chart/ethereum:0x0f38"] * 3
    # Two windows of 450 days from 2024-11-01 reach 2026-11-12, then the recent days: all at midnight UTC, a day apart.
    assert [(kw["params"]["start"], kw["params"]["span"], kw["params"]["period"]) for _, _, kw in http.session.calls[:3]] == [
        (1730419200, 450, "1d"), (1769299200, 450, "1d"), (1793232000, 15, "1d")]
    assert _saved_token_prices(tmp_path, "defillama") == [
        "coingecko_wrapped-bitcoin__2024-11-01.json.gz", "coingecko_wrapped-bitcoin__2026-01-25.json.gz", "coingecko_wrapped-bitcoin__recent.json.gz",
        "ethereum_0x0f38__2024-11-01.json.gz", "ethereum_0x0f38__2026-01-25.json.gz", "ethereum_0x0f38__recent.json.gz"]
    saved = tmp_path / "bronze/defillama/token_price/dt=2026-11-12/ethereum_0x0f38__2024-11-01.json.gz"
    assert gzip.decompress(saved.read_bytes()) == empty  # no price before the coin's first is the source's answer, kept as it arrived
    assert not ctx.warnings


def test_defillama_token_price_reads_only_the_recent_days_once_a_coin_has_them(tmp_path, monkeypatch):
    from ingest.sources import defillama

    BronzeWriter("2026-11-12", root=tmp_path / "bronze").save("defillama", "token_price", "coingecko:wrapped-bitcoin__recent", b"{}", url="u")
    wbtc = _llama_prices("coingecko:wrapped-bitcoin", "WBTC", (1794441600, 73916.0))
    tlo = _llama_prices("ethereum:0x0f38", "TLO", (1794441600, 1.0283))
    ctx, http = _token_price_context(tmp_path, monkeypatch, defillama, [FakeResponse(200, wbtc)] + [FakeResponse(200, tlo)] * 3, snapshot="2026-11-13")
    defillama.token_price(ctx)
    assert [url.rsplit("/", 1)[1] for _, url, _ in http.session.calls] == ["coingecko:wrapped-bitcoin"] + ["ethereum:0x0f38"] * 3
    assert _saved_token_prices(tmp_path, "defillama", "2026-11-13")[:1] == ["coingecko_wrapped-bitcoin__recent.json.gz"]


def test_defillama_token_price_refuses_a_reply_for_another_key_and_survives_a_failed_window(tmp_path, monkeypatch):
    from ingest.sources import defillama

    other_case = _llama_prices("coingecko:Wrapped-Bitcoin", "WBTC", (1794355200, 1.0))  # silver would not find the coin under this key
    tlo = _llama_prices("ethereum:0x0f38", "TLO", (1794355200, 1.0281))
    ctx, _ = _token_price_context(tmp_path, monkeypatch, defillama, [FakeResponse(200, other_case), FakeResponse(500, b"down"), FakeResponse(200, other_case)] + [FakeResponse(200, tlo)] * 3)
    ctx.http.request = lambda method, url, **kw: HttpClient.request(ctx.http, method, url, retries=1, **kw)
    defillama.token_price(ctx)
    assert _saved_token_prices(tmp_path, "defillama") == ["ethereum_0x0f38__2024-11-01.json.gz", "ethereum_0x0f38__2026-01-25.json.gz", "ethereum_0x0f38__recent.json.gz"]
    assert len(ctx.warnings) == 3 and sum("not saved" in w and "coingecko:Wrapped-Bitcoin" in w for w in ctx.warnings) == 2 and sum("gave up" in w for w in ctx.warnings) == 1


def _pool_context(tmp_path, monkeypatch, replies, listed=None, dashboard=None, block_days=None, snapshot="2026-11-12", priced=None):
    """Bronze holds a 1Click token list, one block per {day: height} and, if given, a dashboard reading of [(day, symbol, usd)]."""
    from ingest import sources  # noqa: F401
    from ingest.sources import intents_pool

    bronze = tmp_path / "bronze"
    monkeypatch.setattr("ingest.pipeline.STATE", tmp_path / "state")
    monkeypatch.setattr(intents_pool, "BRONZE", bronze)
    monkeypatch.setattr(intents_pool, "POOL_PAUSE_SECONDS", 0)
    # The price registry lists every asset of the dashboard reading, unless a test names the priced ones itself
    prices = [{"symbol": s, "price_source": "coinmetrics"} for s in (priced if priced is not None else sorted({s for _, s, _ in dashboard or []}))]
    monkeypatch.setattr(intents_pool, "read_registry", lambda name: prices if name == "token_prices" else [
        {"token_id": "wrap.near", "symbol": "wNEAR", "token_class": "native_wrapped", "decimals": "24"},
        {"token_id": "usdt.tether-token.near", "symbol": "USDT", "token_class": "stablecoin", "decimals": "6"}])
    files = {"oneclick/tokens/dt=2026-11-12/all.json.gz": listed if listed is not None else [],
             "rpc/block_day/dt=2026-11-12/all.json.gz": [{"day": d, "height": h} for d, h in (block_days or {}).items()]}
    if dashboard is not None:
        files[f"dune_public/query_results/dt=2026-11-12/{intents_pool.POOL_SHARES_QUERY}__cols-abc.json.gz"] = {
            "execution_succeeded": {"data": [{"date_at": d, "symbol": s, "tvl_usd": usd} for d, s, usd in dashboard]}}
    for name, doc in files.items():
        path = bronze / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(doc).encode()))
    http = client(replies)
    http.policies[intents_pool.ARCHIVAL.split("/")[2]] = HostPolicy()
    return intents_pool, Context(snapshot, http, BronzeWriter(snapshot, root=bronze)), http


def _pool_saved(tmp_path, day, snapshot="2026-11-12"):
    return json.loads(gzip.decompress((tmp_path / f"bronze/rpc/intents_pool_history/dt={snapshot}/{day}.json.gz").read_bytes()))


def _pool_asked(http):
    return [(c[2]["json"]["params"]["block_id"], c[2]["json"]["params"]["account_id"]) for c in http.session.calls]


def test_pool_history_closes_the_day_before_and_each_complete_month_back_to_the_pools_first():
    from ingest.sources.intents_pool import closing_days

    days = closing_days(date(2025, 2, 12))
    assert days == [date(2025, 2, 11), date(2025, 1, 31), date(2024, 12, 31), date(2024, 11, 30)]  # February is not complete
    assert closing_days(date(2025, 2, 1)) == [date(2025, 1, 31), date(2024, 12, 31), date(2024, 11, 30)]  # the day before is a month end


def test_pool_main_assets_are_those_with_a_hundredth_of_the_dashboards_newest_day(tmp_path, monkeypatch):
    dashboard = [("2026-11-10", "OLD", 900), ("2026-11-10", "ZEC", 100),                             # an earlier day does not count
                 ("2026-11-11", "wNEAR", 600), ("2026-11-11", "ZEC", 300), ("2026-11-11", "WBTC", 90),
                 ("2026-11-11", "wBTC", 9.9), ("2026-11-11", "OLD", 0.1)]                            # under 1% of 1,000
    pool, ctx, _ = _pool_context(tmp_path, monkeypatch, [], dashboard=dashboard)
    assert pool.dashboard_assets(ctx.snapshot) == {"wNEAR", "ZEC", "WBTC"}  # spelled as the dashboard spells them
    assert pool.dashboard_assets("2026-11-11") == set()  # no reading the run may see


def test_pool_reads_a_main_asset_only_when_the_price_registry_lists_it(tmp_path, monkeypatch):
    listed = [{"assetId": "nep141:zec.omft.near", "symbol": "ZEC", "decimals": 8, "price": 983.48},
              {"assetId": "nep141:abc.omft.near", "symbol": "ABC", "decimals": 8, "price": 2.0}]
    dashboard = [("2026-11-11", s, usd) for s, usd in (("wNEAR", 500), ("ZEC", 300), ("ABC", 200))]
    pool, ctx, _ = _pool_context(tmp_path, monkeypatch, [], listed=listed, dashboard=dashboard, priced=["ZEC"])
    assert [t["listed_symbol"] for t in pool.pool_tokens(ctx.snapshot) if t["chosen_as"] == "other_asset"] == ["ZEC"]


def test_pool_tokens_come_from_the_registry_the_list_and_the_dashboards_main_assets(tmp_path, monkeypatch):
    listed = [
        {"assetId": "nep141:eth-0xa.omft.near", "symbol": "USDC", "decimals": 6, "price": 0.9995},
        {"assetId": "nep141:eth-0xa.omft.near", "symbol": "USDC", "decimals": 6, "price": 0.9995},       # listed twice: asked once
        {"assetId": "1cs_v1:near:nep141:usdt.tether-token.near", "symbol": "USDT", "decimals": 6, "price": 1},
        {"assetId": "nep245:v2_1.omni.hot.tg:56_abc", "symbol": "USDT(DEPRECATED)", "decimals": 18, "price": 0.9991},
        {"assetId": "nep141:off-peg.omft.near", "symbol": "USDX", "decimals": 6, "price": 0.97},         # more than 2% from a dollar
        {"assetId": "nep141:no-price.omft.near", "symbol": "USDX", "decimals": 6, "price": None},
        {"assetId": "1cs_v1:hypercore:erc20:0xb8", "symbol": "USDC", "decimals": 6, "price": 0.9995},    # not a NEAR token
        {"assetId": "nep141:zec.omft.near", "symbol": "ZEC", "decimals": 8, "price": 983.48},            # a main asset of the pool
        {"assetId": "1cs_v1:sol:spl:A7bd", "symbol": "ZEC", "decimals": 8, "price": 983.48},             # the same asset, not on NEAR
        {"assetId": "nep245:v2_1.omni.hot.tg:10_eth", "symbol": "ETH_(DEPRECATED)", "decimals": 18, "price": 2045},
        {"assetId": "nep141:f.bridge.near", "symbol": "wBTC", "decimals": 8, "price": 73438},            # the dashboard's wBTC is another, smaller asset
        {"assetId": "nep141:small.omft.near", "symbol": "DOGE", "decimals": 8, "price": 0.07},           # under 1% of the pool
        {"assetId": "nep141:wrap.near", "symbol": "wNEAR", "decimals": 24, "price": 3.47},
    ]
    dashboard = [("2026-11-11", s, usd) for s, usd in (("wNEAR", 500), ("USDC", 300), ("ZEC", 100), ("ETH", 60), ("WBTC", 35), ("wBTC", 4), ("DOGE", 1))]
    pool, ctx, _ = _pool_context(tmp_path, monkeypatch, [], listed=listed, dashboard=dashboard)
    tokens = pool.pool_tokens(ctx.snapshot)
    assert [(t["asset_id"], t["chosen_as"], t["listed_symbol"], t["decimals"]) for t in tokens] == [
        ("nep141:wrap.near", "wrapped_near", "wNEAR", 24),                               # from the registry, never from a price
        ("nep141:eth-0xa.omft.near", "dollar_token", "USDC", 6),
        ("nep141:usdt.tether-token.near", "dollar_token", "USDT", 6),
        ("nep245:v2_1.omni.hot.tg:56_abc", "dollar_token", "USDT(DEPRECATED)", 18),
        ("nep141:zec.omft.near", "other_asset", "ZEC", 8),
        ("nep245:v2_1.omni.hot.tg:10_eth", "other_asset", "ETH_(DEPRECATED)", 18),       # matched without 1Click's mark
    ]
    assert tokens[3]["contract"] == "v2_1.omni.hot.tg" and tokens[3]["token_id"] == "56_abc"
    assert "listed_price" in tokens[1] and "listed_price" not in tokens[4]  # no price travels with a token that is not a dollar


def test_pool_tokens_are_wnear_and_dollars_alone_without_a_dashboard_reading(tmp_path, monkeypatch):
    listed = [{"assetId": "nep141:eth-0xa.omft.near", "symbol": "USDC", "decimals": 6, "price": 1.0},
              {"assetId": "nep141:zec.omft.near", "symbol": "ZEC", "decimals": 8, "price": 983.48}]
    pool, ctx, _ = _pool_context(tmp_path, monkeypatch, [], listed=listed)
    assert [t["asset_id"] for t in pool.pool_tokens(ctx.snapshot)] == ["nep141:wrap.near", "nep141:eth-0xa.omft.near"]


def test_pool_history_skips_until_there_is_a_token_list(tmp_path, monkeypatch):
    pool, ctx, _ = _pool_context(tmp_path, monkeypatch, [], block_days={"2026-11-12": 900})
    (tmp_path / "bronze/oneclick/tokens/dt=2026-11-12/all.json.gz").unlink()
    with pytest.raises(Skip):
        pool.intents_pool_history(ctx)


def test_pool_history_reads_each_token_at_the_block_that_closes_the_day(tmp_path, monkeypatch):
    listed = [{"assetId": "nep141:eth-0xa.omft.near", "symbol": "USDC", "decimals": 6, "price": 1.0},
              {"assetId": "nep245:hot.tg:1_a", "symbol": "USDT", "decimals": 6, "price": 1.0},
              {"assetId": "nep245:hot.tg:2_b", "symbol": "USDC(DEPRECATED)", "decimals": 18, "price": 1.0}]
    replies = [_view_reply("17000000000000000000000000000000"), _view_reply("250"), _view_reply(["7", "0"])]
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, replies, listed=listed, block_days={"2026-11-12": 900})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 11, 30))  # no month end yet: only the day before the snapshot
    pool.intents_pool_history(ctx)
    asked = [json.loads(json.dumps(c[2]["json"]))["params"] for c in http.session.calls]
    assert [(p["block_id"], p["account_id"], p["method_name"]) for p in asked] == [
        (900, "wrap.near", "ft_balance_of"), (900, "eth-0xa.omft.near", "ft_balance_of"), (900, "hot.tg", "mt_batch_balance_of")]
    assert json.loads(base64.b64decode(asked[0]["args_base64"])) == {"account_id": "intents.near"}
    assert json.loads(base64.b64decode(asked[2]["args_base64"])) == {"account_id": "intents.near", "token_ids": ["1_a", "2_b"]}
    saved = _pool_saved(tmp_path, "2026-11-11")
    assert (saved["closes_day"], saved["block_day"], saved["block_height"], saved["account_id"]) == ("2026-11-11", "2026-11-12", 900, "intents.near")
    assert [(b["asset_id"], b["balance"]) for b in saved["balances"]] == [
        ("nep141:wrap.near", "17000000000000000000000000000000"),  # text, so a yocto amount keeps every digit
        ("nep141:eth-0xa.omft.near", "250"), ("nep245:hot.tg:1_a", "7"), ("nep245:hot.tg:2_b", "0")]
    assert saved["balances"][3]["listed_symbol"] == "USDC(DEPRECATED)" and saved["balances"][3]["decimals"] == 18
    pool.intents_pool_history(ctx)
    assert len(http.session.calls) == 3  # every token has its answer on file


def test_pool_history_asks_token_by_token_where_a_contract_has_no_view_for_all(tmp_path, monkeypatch):
    listed = [{"assetId": "nep245:hot.tg:1_a", "symbol": "USDT", "decimals": 6, "price": 1.0},
              {"assetId": "nep245:hot.tg:2_b", "symbol": "USDC", "decimals": 6, "price": 1.0}]
    no_method = FakeResponse(200, json.dumps({"result": {"block_height": 1, "logs": [], "error": "wasm execution failed with error: MethodResolveError(MethodNotFound)"}}).encode())
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, [_view_reply("9"), no_method, _view_reply("7"), no_method],
                                    listed=listed, block_days={"2026-11-12": 900})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 11, 30))
    pool.intents_pool_history(ctx)
    asked = [json.loads(json.dumps(c[2]["json"]))["params"] for c in http.session.calls]
    assert [p["method_name"] for p in asked] == ["ft_balance_of", "mt_batch_balance_of", "mt_balance_of", "mt_balance_of"]
    assert json.loads(base64.b64decode(asked[2]["args_base64"])) == {"account_id": "intents.near", "token_id": "1_a"}
    saved = _pool_saved(tmp_path, "2026-11-11")["balances"]
    assert [(b["asset_id"], b["balance"], b.get("error")) for b in saved[1:]] == [
        ("nep245:hot.tg:1_a", "7", None), ("nep245:hot.tg:2_b", None, "CONTRACT_EXECUTION_ERROR")]  # the second token's own view failed too


def test_pool_history_names_no_person_or_project_and_sends_no_key(tmp_path, monkeypatch):
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, [_view_reply("1")], block_days={"2026-11-12": 900})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 11, 30))
    monkeypatch.setenv("FASTNEAR_API_KEY", "test-value")
    pool.intents_pool_history(ctx)
    call = http.session.calls[0][2]
    assert call["headers"] == {"User-Agent": "python-requests"}
    assert "near-hub" not in json.dumps(call["json"]) and "test-value" not in json.dumps(call)


def test_pool_history_reads_month_ends_newest_first_and_keeps_the_chains_own_refusals(tmp_path, monkeypatch):
    listed = [{"assetId": "nep141:new.omft.near", "symbol": "USDC", "decimals": 6, "price": 1.0}]
    replies = [_view_reply("3"), _view_reply("40"),               # 2026-11-11
               _view_reply("2"), _view_error("UNKNOWN_ACCOUNT"),  # 2026-10-31
               _view_reply("1"), _view_error("UNKNOWN_ACCOUNT"),  # 2026-09-30
               _view_reply("0")]                                  # 2026-08-31: absent on two newer days, so not asked
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, replies, listed=listed,
                                    block_days={"2026-11-12": 900, "2026-11-01": 800, "2026-10-01": 700, "2026-09-01": 600})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 8, 31))
    pool.intents_pool_history(ctx)
    assert _pool_asked(http) == [(900, "wrap.near"), (900, "new.omft.near"), (800, "wrap.near"), (800, "new.omft.near"),
                                 (700, "wrap.near"), (700, "new.omft.near"), (600, "wrap.near")]
    october = _pool_saved(tmp_path, "2026-10-31")["balances"]
    assert (october[1]["balance"], october[1]["error"]) == (None, "UNKNOWN_ACCOUNT")
    assert [b["asset_id"] for b in _pool_saved(tmp_path, "2026-08-31")["balances"]] == ["nep141:wrap.near"]
    pool.intents_pool_history(ctx)
    assert len(http.session.calls) == 7  # the absent contract is not asked about again on a later run


def test_pool_history_reads_a_token_that_joins_the_list_at_the_days_already_on_file(tmp_path, monkeypatch):
    usdc = {"assetId": "nep141:eth-0xa.omft.near", "symbol": "USDC", "decimals": 6, "price": 1.0}
    zec = {"assetId": "nep141:zec.omft.near", "symbol": "ZEC", "decimals": 8, "price": 983.48}
    replies = [_view_reply("5"), _view_reply("50"), _view_reply("4"), _view_reply("40"),  # wNEAR and USDC on two days
               _view_reply("700"), _view_reply("600"),                                    # ZEC on the same two days, a run later
               _view_reply("6"), _view_reply("60"), _view_reply("800")]                   # a night later: one new day, all three
    block_days = {"2026-11-12": 900, "2026-11-01": 800}
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, replies, listed=[usdc, zec], block_days=block_days, priced=["ZEC"])
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 10, 31))
    pool.intents_pool_history(ctx)
    assert len(http.session.calls) == 4  # ZEC is listed, but no dashboard reading names it a main asset yet
    reading = tmp_path / f"bronze/dune_public/query_results/dt=2026-11-12/{pool.POOL_SHARES_QUERY}__cols-abc.json.gz"
    reading.parent.mkdir(parents=True)
    reading.write_bytes(gzip.compress(json.dumps({"execution_succeeded": {"data": [{"date_at": "2026-11-11", "symbol": "ZEC", "tvl_usd": 1}]}}).encode()))
    pool.intents_pool_history(ctx)
    assert _pool_asked(http)[4:] == [(900, "zec.omft.near"), (800, "zec.omft.near")]  # only what has no answer yet
    saved = _pool_saved(tmp_path, "2026-10-31")["balances"]  # the same snapshot's file gains the token and keeps the rest
    assert [(b["asset_id"], b["balance"], b["chosen_as"]) for b in saved] == [
        ("nep141:wrap.near", "4", "wrapped_near"), ("nep141:eth-0xa.omft.near", "40", "dollar_token"), ("nep141:zec.omft.near", "600", "other_asset")]
    manifest = [json.loads(line) for line in (tmp_path / "bronze/_manifest/dt=2026-11-12.jsonl").read_text().splitlines()]
    assert [e["rows"] for e in manifest if e["dataset"] == "intents_pool_history"] == [3, 3]  # one line per file, for the file as it now is
    with (tmp_path / "bronze/rpc/block_day/dt=2026-11-12/later.json.gz").open("wb") as f:
        f.write(gzip.compress(json.dumps([{"day": "2026-11-13", "height": 950}]).encode()))
    later = Context("2026-11-13", http, BronzeWriter("2026-11-13", root=tmp_path / "bronze"))
    pool.intents_pool_history(later)
    assert _pool_asked(http)[6:] == [(950, "wrap.near"), (950, "eth-0xa.omft.near"), (950, "zec.omft.near")]
    assert sorted(p.name for p in (tmp_path / "bronze/rpc/intents_pool_history/dt=2026-11-13").iterdir()) == ["2026-11-12.json.gz"]


def test_pool_history_leaves_a_day_unsaved_when_a_node_cannot_answer(tmp_path, monkeypatch):
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, [_view_error("UNKNOWN_BLOCK"), _view_reply("5")], block_days={"2026-11-12": 900})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 11, 30))
    pool.intents_pool_history(ctx)
    assert not (tmp_path / "bronze/rpc/intents_pool_history").exists() and "UNKNOWN_BLOCK" in ctx.warnings[0]
    pool.intents_pool_history(ctx)  # a later run reads the day
    assert _pool_saved(tmp_path, "2026-11-11")["balances"][0]["balance"] == "5"


def test_pool_history_refuses_a_reply_that_is_not_a_balance(tmp_path, monkeypatch):
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, [_view_reply({"balance": "5"})], block_days={"2026-11-12": 900})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 11, 30))
    pool.intents_pool_history(ctx)
    assert not (tmp_path / "bronze/rpc/intents_pool_history").exists() and "not 1 balances" in ctx.warnings[0]


def test_pool_history_stops_when_the_endpoint_refuses(tmp_path, monkeypatch):
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, [FakeResponse(403, b"forbidden"), _view_reply("5")],
                                    block_days={"2026-11-12": 900, "2026-11-01": 800})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 10, 31))
    pool.intents_pool_history(ctx)
    assert len(http.session.calls) == 1 and "HTTP 403" in ctx.warnings[0] and "stopped" in ctx.warnings[0]
    assert not (tmp_path / "bronze/rpc/intents_pool_history").exists()


def test_pool_history_waits_once_for_a_busy_endpoint_and_then_stops_for_the_run(tmp_path, monkeypatch):
    replies = [_view_reply("5"),                                  # 2026-11-11 is read
               FakeResponse(429), FakeResponse(429),              # 2026-10-31: refused, and refused again after the wait
               _view_reply("4"), _view_reply("3")]                # the next run
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, replies, block_days={"2026-11-12": 900, "2026-11-01": 800, "2026-10-01": 700})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 9, 30))
    pool.intents_pool_history(ctx)
    assert len(http.session.calls) == 3 and "stopped" in ctx.warnings[0]  # September is not asked about
    assert _pool_saved(tmp_path, "2026-11-11")["balances"][0]["balance"] == "5"
    assert not (tmp_path / "bronze/rpc/intents_pool_history/dt=2026-11-12/2026-10-31.json.gz").exists()
    pool.intents_pool_history(ctx)  # a later run goes on where this one stopped
    assert [_pool_saved(tmp_path, day)["balances"][0]["balance"] for day in ("2026-10-31", "2026-09-30")] == ["4", "3"]


def test_pool_history_reads_a_batch_of_days_a_run(tmp_path, monkeypatch):
    block_days = {"2026-11-12": 900, "2026-11-01": 800, "2026-10-01": 700}
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, [_view_reply(str(n)) for n in (3, 2, 1)], block_days=block_days)
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 9, 30))
    monkeypatch.setattr(pool, "POOL_DAYS_PER_RUN", 2)
    pool.intents_pool_history(ctx)
    assert _pool_asked(http) == [(900, "wrap.near"), (800, "wrap.near")]
    pool.intents_pool_history(ctx)
    assert _pool_asked(http)[2:] == [(700, "wrap.near")]


def test_pool_history_warns_when_the_closing_block_is_unknown(tmp_path, monkeypatch):
    pool, ctx, http = _pool_context(tmp_path, monkeypatch, [], block_days={"2026-11-01": 800})
    monkeypatch.setattr(pool, "FIRST_MONTH_END", date(2026, 11, 30))
    pool.intents_pool_history(ctx)
    assert ctx.warnings == ["2026-11-11: no block height known yet for 2026-11-12"] and http.session.calls == []


def test_block_heights_and_the_token_list_come_before_the_pool_history():
    from ingest import sources  # noqa: F401
    from ingest.pipeline import select

    names = [f"{d.source}/{d.name}" for d in select("all", None, None)]
    for earlier in ("rpc/block_day", "oneclick/tokens"):
        assert names.index(earlier) < names.index("rpc/intents_pool_history")


def test_forum_threads_are_saved_without_posts_or_authors(tmp_path):
    from ingest.sources.ecosystem import GOV_TOPIC_FIELDS, gov_topics
    reply = {"id": 1, "title": "t", "created_at": "2026-01-01T00:00:00Z", "last_posted_at": "2026-01-02T00:00:00Z", "posts_count": 2,
             "views": 3, "like_count": 4, "closed": False, "details": {"participants": [{"username": "someone"}]},
             "post_stream": {"posts": [{"name": "Some One", "username": "someone", "avatar_template": "/a.png", "cooked": "<p>text</p>"}]}}
    http = client([FakeResponse(body=json.dumps(reply).encode()) for _ in range(4)])
    http.policies = {}
    ctx = Context("2026-11-14", http, BronzeWriter("2026-11-14", root=tmp_path))
    gov_topics(ctx)
    ctx.bronze.flush()
    saved = sorted((tmp_path / "gov" / "topics" / "dt=2026-11-14").glob("*.json.gz"))
    assert len(saved) == 4
    for path in saved:
        raw = gzip.decompress(path.read_bytes()).decode()
        assert set(json.loads(raw)) == set(GOV_TOPIC_FIELDS)
        assert "someone" not in raw and "cooked" not in raw
