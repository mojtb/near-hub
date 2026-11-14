"""Save widgets read in a browser from NEAR's public Intents dashboard on Dune into bronze, with credit.

Results are public, but Dune's terms bar bots, scrapers and access other than through its own interface, so
this is meant as a manual step: a person opens the dashboard in their own browser, lets every widget load, and saves
the Network tab as a HAR file. Never schedule it. The readings stored so far were not taken that way: an AI-driven
browser took them at the owner's request, as each manifest note and docs/SOURCES.md record, and registry/sources.csv
asks for a reading by hand to replace them.

From the HAR this keeps each widget's response exactly as received, plus the query id, the dashboard's filter
values and the columns asked for. Everything else stays behind, including headers, cookies and the page's
timestamp and signature. The HAR itself stays out of the repository: .gitignore covers it.

A table shows 25 rows at a time and asks for each page separately, so page through it before saving: each page
is kept under its row offset. A tile first asks for one row and then for its value, so each widget keeps its
fullest response, never a shorter one that came later.

Usage: python -m tools.record_dune_reading <reading.har> <snapshot-date> "<how it was read>"
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ingest.bronze import BronzeWriter, safe_key
from ingest.settings import BRONZE, ROOT

ENDPOINT = "https://dune.com/public/execution"
CREDIT = "Derived from the NEAR Intents dashboard on Dune by @near, https://dune.com/near/near-intents"
MAX_SELECTION = 100


def _values(parameter: dict) -> list:
    return parameter["values"] if "values" in parameter else [parameter.get("value")]


def widget_key(query_id: int, parameters: List[dict], columns: List[str], offset: int = 0) -> str:
    """Query id, filter values, a table page's row offset after the first page, then a hash of the columns,
    because one query can feed several widgets."""
    chosen = "__".join(f"{p['key']}-{'+'.join(str(v) for v in _values(p))}" for p in sorted(parameters, key=lambda p: p["key"]))
    selection = safe_key(chosen) if chosen else ""
    if len(selection) > MAX_SELECTION:
        selection = f"{selection[:MAX_SELECTION]}-{hashlib.sha256(selection.encode()).hexdigest()[:8]}"
    page = f"offset-{offset}" if offset else ""
    columns_hash = hashlib.sha256(",".join(columns).encode()).hexdigest()[:6]
    return "__".join(part for part in (str(query_id), selection, page, f"cols-{columns_hash}") if part)


def _response_bytes(entry: dict) -> Optional[bytes]:
    content = entry["response"].get("content") or {}
    text = content.get("text")
    if text is None:
        return None
    return base64.b64decode(text) if content.get("encoding") == "base64" else text.encode()


def collect(har: dict) -> Tuple[Dict[str, dict], int]:
    """The fullest finished response per widget (the later one on a tie), and how many calls to the endpoint gave
    no usable result."""
    widgets: Dict[str, dict] = {}
    unfinished = 0
    for entry in har["log"]["entries"]:
        request = entry["request"]
        if request["url"].split("?", 1)[0] != ENDPOINT:
            continue
        raw = _response_bytes(entry) if entry["response"].get("status") == 200 else None
        body = (request.get("postData") or {}).get("text")
        result = json.loads(raw).get("execution_succeeded") if raw else None
        if not result or not body:
            unfinished += 1
            continue
        asked = json.loads(body)
        parameters = asked.get("parameters") or []
        columns = asked.get("output_columns") or result["columns"]
        offset = int((asked.get("pagination") or {}).get("offset") or 0)
        key = widget_key(asked["query_id"], parameters, columns, offset)
        if key in widgets and widgets[key]["rows"] > len(result["data"]):
            continue
        params = {"query_id": asked["query_id"],
                  "parameters": [{"key": p["key"], "values": _values(p)} for p in parameters],
                  "output_columns": columns,
                  "execution_id": result["execution_id"],
                  "generated_at": result["generated_at"]}
        if offset:
            params["row_offset"] = offset
        widgets[key] = {"raw": raw, "params": params, "rows": len(result["data"]),
                        "total_rows": result.get("total_row_count", len(result["data"]))}
    return widgets, unfinished


def record(har_path: str, snapshot: str, how: str, root: Path = BRONZE, pinned: Path = ROOT / "data" / "PINNED") -> Dict[str, dict]:
    pin = pinned.read_text().strip()
    if snapshot > pin:
        raise SystemExit(f"{snapshot} is after main's pin, {pin}. Move the pin first (see docs/ARCHITECTURE.md): "
                         "up to the pin main's bronze is the record, so a later reading would clash with that date's nightly data.")
    widgets, unfinished = collect(json.loads(Path(har_path).read_text()))
    if not widgets:
        raise SystemExit("No finished widget responses in this file. Let every widget load, then save the Network tab again.")
    writer = BronzeWriter(snapshot, root=root)
    for key, widget in sorted(widgets.items()):
        partial = "" if widget["rows"] >= widget["total_rows"] else f"; partial, {widget['rows']} of {widget['total_rows']} rows"
        writer.save("dune_public", "query_results", key, widget["raw"], url=ENDPOINT, method="POST", params=widget["params"],
                    rows=widget["rows"], note=f"{CREDIT}. {how}; not through the API{partial}")
    writer.flush()
    partials = sum(1 for w in widgets.values() if w["rows"] < w["total_rows"])
    print(f"Saved {len(widgets)} widgets as dt={snapshot}; {partials} partial, {unfinished} calls had no finished result")
    return widgets


if __name__ == "__main__":
    record(sys.argv[1], sys.argv[2], sys.argv[3])
