"""Command line: `python -m ingest run` and `python -m ingest list`."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import sources  # noqa: F401  (importing registers every dataset)
from .pipeline import REGISTRY, print_summary, run, select
from .settings import load_dotenv


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="ingest", description="Fetch NEAR data into data/bronze.")
    sub = parser.add_subparsers(dest="command", required=True)
    run_cmd = sub.add_parser("run", help="fetch datasets")
    run_cmd.add_argument("--profile", default="nightly", choices=["nightly", "backfill", "all"])
    run_cmd.add_argument("--sources", help="comma-separated sources, default all")
    run_cmd.add_argument("--datasets", help="comma-separated dataset names, default all")
    run_cmd.add_argument("--date", help="snapshot date YYYY-MM-DD, default today UTC")
    sub.add_parser("list", help="show every dataset")
    args = parser.parse_args()

    if args.command == "list":
        for d in REGISTRY:
            needs = f" (needs {', '.join(d.requires)})" if d.requires else ""
            print(f"{d.profile:<9} {d.source}/{d.name}{needs}")
        return 0

    snapshot = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    chosen = select(args.profile, args.sources.split(",") if args.sources else None,
                    args.datasets.split(",") if args.datasets else None)
    if not chosen:
        print("Nothing matched the selection.", file=sys.stderr)
        return 2
    results = run(snapshot, chosen)
    print_summary(results)
    # A run that saved nothing at all is a failure; a partly failed run is reported but still kept.
    return 0 if any(r["status"] in ("ok", "partial") for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
