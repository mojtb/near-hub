"""Tests for the manual Dune reading and the start of the nightly job. They need no network and no warehouse."""
from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

import pytest

from tools.bring_in_nightly import drop_up_to
from tools.record_dune_reading import CREDIT, ENDPOINT, collect, record, widget_key

REPO = Path(__file__).resolve().parents[1]
PRIVATE = "do-not-keep"
PARAMETERS = [{"type": "enum", "key": "symbol", "values": ["ALL"], "enumFromResults": {"queryId": 5358748}},
              {"type": "enum", "key": "blockchain", "values": ["ALL"], "isMultiselect": True}]
COLUMNS = ["date_at", "symbol", "volume_usd"]
ASKED = {"execution_id": "E1", "query_id": 5175131, "parameters": PARAMETERS, "output_columns": COLUMNS, "ts": 1793573780302, "s": PRIVATE}


def _succeeded(rows=2, total=None, generated="2026-11-01T20:56:23Z") -> dict:
    data = [{"date_at": "2026-10-31", "symbol": f"S{i}", "volume_usd": 1.5} for i in range(rows)]
    return {"execution_queued": None, "execution_running": None, "execution_failed": None,
            "execution_succeeded": {"execution_id": "E1", "generated_at": generated, "columns": COLUMNS, "data": data,
                                    "total_row_count": rows if total is None else total}}


def _entry(asked=ASKED, response=None, url=ENDPOINT, status=200) -> dict:
    body = json.dumps(_succeeded() if response is None else response)
    return {"request": {"url": url, "method": "POST", "headers": [{"name": "cookie", "value": PRIVATE}], "postData": {"text": json.dumps(asked)}},
            "response": {"status": status, "headers": [{"name": "set-cookie", "value": PRIVATE}], "content": {"text": body}}}


def _har(*entries) -> dict:
    return {"log": {"entries": list(entries)}}


def _record(tmp_path, *entries, snapshot="2026-11-01", pin="2026-11-01"):
    (tmp_path / "PINNED").write_text(pin + "\n")
    har = tmp_path / "reading.har"
    har.write_text(json.dumps(_har(*entries)))
    record(str(har), snapshot, "read by hand", root=tmp_path / "bronze", pinned=tmp_path / "PINNED")
    return tmp_path / "bronze"


def test_reading_keeps_the_response_exactly_and_nothing_private(tmp_path):
    entry = _entry()
    bronze = _record(tmp_path, entry)
    saved = list((bronze / "dune_public" / "query_results" / "dt=2026-11-01").glob("*.json.gz"))
    assert len(saved) == 1
    assert gzip.decompress(saved[0].read_bytes()) == entry["response"]["content"]["text"].encode()
    manifest = (bronze / "_manifest" / "dt=2026-11-01.jsonl").read_text()
    assert PRIVATE not in manifest and str(ASKED["ts"]) not in manifest
    line = json.loads(manifest)
    assert CREDIT in line["note"] and "not through the API" in line["note"]
    assert line["params"]["query_id"] == 5175131 and line["rows"] == 2
    assert {"key": "symbol", "values": ["ALL"]} in line["params"]["parameters"]


def test_reading_reads_a_base64_response(tmp_path):
    entry = _entry()
    raw = entry["response"]["content"]["text"].encode()
    entry["response"]["content"] = {"text": base64.b64encode(raw).decode(), "encoding": "base64"}
    widgets, _ = collect(_har(entry))
    assert [w["raw"] for w in widgets.values()] == [raw]


def test_reading_keeps_the_last_finished_response_per_widget():
    widgets, _ = collect(_har(_entry(response=_succeeded(rows=1)), _entry(response=_succeeded(rows=3))))
    assert [w["rows"] for w in widgets.values()] == [3]


def test_reading_never_lets_a_shorter_later_response_replace_a_fuller_one():
    widgets, _ = collect(_har(_entry(response=_succeeded(rows=3)), _entry(response=_succeeded(rows=1, total=3))))
    assert [w["rows"] for w in widgets.values()] == [3]


def test_reading_keeps_every_page_of_a_table(tmp_path):
    def page(offset):
        return _entry(asked={**ASKED, "parameters": [], "output_columns": None, "pagination": {"limit": 2, "offset": offset}},
                      response=_succeeded(rows=2, total=4))
    widgets, _ = collect(_har(page(0), page(2)))
    first, second = sorted(widgets)
    assert first == widget_key(5175131, [], COLUMNS) and second == widget_key(5175131, [], COLUMNS, 2)
    assert "__offset-2__cols-" in second and "offset" not in first
    assert widgets[second]["params"]["row_offset"] == 2 and "row_offset" not in widgets[first]["params"]


def test_reading_skips_other_requests_and_unfinished_results():
    running = {"execution_queued": None, "execution_running": {"execution_id": "E1"}, "execution_succeeded": None}
    widgets, unfinished = collect(_har(_entry(url="https://dune.com/public/other"), _entry(response=running), _entry(status=429), _entry()))
    assert len(widgets) == 1 and unfinished == 2


def test_widgets_stay_apart_by_filter_and_by_columns():
    base = widget_key(5175131, PARAMETERS, COLUMNS)
    assert base.startswith("5175131__blockchain-ALL__symbol-ALL__cols-")
    assert widget_key(5175131, list(reversed(PARAMETERS)), COLUMNS) == base
    assert widget_key(5175131, [{"key": "blockchain", "values": ["near"]}, PARAMETERS[0]], COLUMNS) != base
    assert widget_key(5175131, PARAMETERS, COLUMNS[:2]) != base
    assert widget_key(5175131, [], COLUMNS).startswith("5175131__cols-")
    assert len(widget_key(5175131, [{"key": "symbol", "values": ["X" * 40] * 30}], COLUMNS)) < 140


def test_reading_says_when_a_widget_returned_only_part_of_its_rows(tmp_path):
    bronze = _record(tmp_path, _entry(response=_succeeded(rows=2, total=10)))
    line = json.loads((bronze / "_manifest" / "dt=2026-11-01.jsonl").read_text())
    assert "partial, 2 of 10 rows" in line["note"]


def test_reading_refuses_a_date_after_the_pin(tmp_path):
    with pytest.raises(SystemExit, match="after main's pin"):
        _record(tmp_path, _entry(), snapshot="2026-11-02", pin="2026-11-01")


def test_reading_refuses_a_file_with_nothing_finished(tmp_path):
    with pytest.raises(SystemExit, match="No finished widget"):
        _record(tmp_path, _entry(status=403))


def test_asset_table_reads_the_widget_this_tool_names():
    sql = (REPO / "warehouse" / "models" / "gold" / "intents" / "fct_dune_intents_asset_daily.sql").read_text()
    assert f"'{widget_key(5175131, PARAMETERS, COLUMNS)}'" in sql


def test_nightly_start_drops_only_what_main_is_the_record_for(tmp_path):
    earlier = ["rpc/block_day/dt=2026-11-01/a.json.gz", "_manifest/dt=2026-11-01.jsonl", "_runs/dt=2026-10-28.json"]
    later = ["rpc/block_day/dt=2026-11-02/a.json.gz", "_manifest/dt=2026-11-02.jsonl", "_runs/dt=2026-11-02.json"]
    for relative in earlier + later:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x")
    assert drop_up_to(tmp_path, "2026-11-01") == 3
    assert not any((tmp_path / relative).exists() for relative in earlier)
    assert all((tmp_path / relative).exists() for relative in later)


def test_years_to_breakeven_is_compound_growth_and_none_when_volume_is_not_growing():
    from tools.horizon import years_to

    assert years_to(4.0, 1.0) == pytest.approx(2.0)
    assert years_to(0.9, 0.5) == 0.0
    assert years_to(3.0, 0.0) is None
    assert years_to(3.0, -0.1) is None
