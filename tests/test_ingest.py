"""Unit tests for the ingest layer. They need no network: HTTP calls go to a stub session."""
from __future__ import annotations

import gzip
import hashlib
import json
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
