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
    if not Path("data/warehouse.duckdb").exists():
        print("data/warehouse.duckdb is missing: run `make warehouse` first")
        return 1
    try:
        result = duckdb.connect("data/warehouse.duckdb", read_only=True).execute(sql)
    except duckdb.Error as error:  # a typo in the query: say what DuckDB said, without a traceback
        print(f"The query did not run. DuckDB says:\n{error}")
        return 1
    if result is None or result.description is None:
        print("The statement returned no rows (was it only a comment?)")
        return 1
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
    sql = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].strip() else ("" if sys.stdin.isatty() else sys.stdin.read())
    if not sql.strip():
        sys.exit('Give a query: make query SQL="select * from gold.fct_mpc_state limit 5", or make query < q.sql')
    sys.exit(main(sql))
