"""Unit tests for the ingest layer. They need no network: HTTP calls go to a stub session."""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date
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
    ctx.save_state("intents_explorer__daily_tally", {"days": {"2026-10-31": 5, "2026-10-30": 5}, "history_starts": None})
    intents.explorer_daily_tally(ctx)
    state = ctx.load_state("intents_explorer__daily_tally")
    assert state["days"] == {"2026-10-31": 1, "2026-10-30": 5, "2026-10-29": 1}


def test_explorer_finds_where_history_starts_and_stays_above_it(tmp_path, monkeypatch):
    intents, ctx, http = _explorer_context(tmp_path, monkeypatch, [[_swap(DAY_START + 1, "a")], [], []])
    monkeypatch.setattr(intents, "EXPLORER_EMPTY_DAYS_TO_STOP", 2)
    intents.explorer_daily_tally(ctx)
    assert ctx.load_state("intents_explorer__daily_tally")["history_starts"] == "2026-10-31"
    assert len(http.session.calls) == 3
    assert not (tmp_path / "bronze/intents_explorer/daily_tally/dt=2026-11-01/2026-10-30.json.gz").exists()


def test_explorer_keeps_a_finished_day_when_a_later_call_fails(tmp_path, monkeypatch):
    intents, ctx, http = _explorer_context(tmp_path, monkeypatch, [[_swap(DAY_START + 1, "a")]])
    http.session.replies.append(FakeResponse(400, b"bad request"))
    intents.explorer_daily_tally(ctx)
    assert ctx.load_state("intents_explorer__daily_tally")["days"] == {"2026-10-31": 1}
    assert ctx.warnings and "2026-10-30" in ctx.warnings[0]


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
