"""Save a dated reading of the public NEAR Intents dashboard on Dune into bronze.

Dune's free access is view-only and has no API, so without a key that includes API access the only
route to these numbers is to read the public page. Dune's terms bar bots and scrapers, so this must
stay a manual step: a person reads the page and writes a JSON file with `tiles` and `fee_channels`.
Never schedule it or drive it from a script. Prefer `dune/query_results` once a key is available.
This tool validates the file's shape, then stores it with a note saying how it was obtained.
tools/record_dune_reading.py keeps each widget's raw response instead, so use that for new readings.

Usage: python -m tools.record_dune_page <reading.json> <snapshot-date> "<how it was read>"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ingest.bronze import BronzeWriter

DASHBOARD = "https://dune.com/near/near-intents"
SCOPES = {"all", "public", "confidential"}


def main(path: str, snapshot: str, how: str) -> None:
    reading = json.loads(Path(path).read_text())
    for tile in reading["tiles"]:
        if tile["scope"] not in SCOPES or not isinstance(tile["value_usd"], (int, float)):
            raise SystemExit(f"bad tile: {tile}")
    channels = [c["referral"] for c in reading["fee_channels"]]
    if len(channels) != len(set(channels)):
        raise SystemExit("duplicate referral in fee_channels")
    writer = BronzeWriter(snapshot)
    writer.save_json("dune_public", "near_intents_dashboard", "page", reading, url=DASHBOARD,
                     rows=len(reading["tiles"]) + len(channels),
                     note=f"{how}; not through the API; tile values are as displayed, rounded to whole dollars")
    writer.flush()
    print(f"Saved {len(reading['tiles'])} tiles and {len(channels)} fee channels as dt={snapshot}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
