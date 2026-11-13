"""Run one SQL query against the warehouse and print the result as a table.

Usage: python -m tools.query "select * from gold.fct_mpc_state limit 5"
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]


def _format(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:,.4f}" if abs(value) < 1000 else f"{value:,.0f}"
    return str(value)


def main(sql: str) -> int:
    os.chdir(ROOT)
    result = duckdb.connect("data/warehouse.duckdb", read_only=True).execute(sql)
    columns = [d[0] for d in result.description]
    rows = [[_format(v) for v in row] for row in result.fetchall()]
    widths = [max([len(c)] + [len(r[i]) for r in rows]) for i, c in enumerate(columns)]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))
    print(f"\n{len(rows)} rows")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or not sys.argv[1].strip():
        sys.exit('Give a query: make query SQL="select * from gold.fct_mpc_state limit 5"')
    sys.exit(main(sys.argv[1]))
