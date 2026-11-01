"""Export every gold table to data/gold/ as Parquet, plus CSV for small tables, and fingerprint them.

A fingerprint is a row count and a hash of every row, with doubles rounded to 7 significant digits so
tiny floating-point differences between machines do not matter. `make verify` recomputes them and
compares with data/gold/_fingerprints.json, which shows a rebuild reproduced the committed tables.

Usage: python -m tools.export_gold [--write-fingerprints]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
GOLD = ROOT / "data" / "gold"
FINGERPRINTS = GOLD / "_fingerprints.json"
CSV_MAX_ROWS = 5000


def gold_tables(con: duckdb.DuckDBPyConnection) -> List[str]:
    rows = con.execute("select table_name from information_schema.tables where table_schema = 'gold' order by 1").fetchall()
    return [r[0] for r in rows]


def _normalized(column: str, data_type: str) -> str:
    quoted = f'"{column}"'
    if data_type in ("DOUBLE", "FLOAT", "REAL"):
        return f"coalesce(printf('%.6e', {quoted}), 'null')"
    return f"coalesce(cast({quoted} as varchar), 'null')"


def fingerprint(con: duckdb.DuckDBPyConnection, table: str) -> Dict[str, object]:
    columns = con.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema = 'gold' and table_name = ? order by ordinal_position", [table]).fetchall()
    parts = ", ".join(_normalized(c, t) for c, t in columns)
    row_count, digest = con.execute(
        f"select count(*), coalesce(md5(string_agg(h, '' order by h)), 'empty') "
        f"from (select md5(concat_ws('|', {parts})) as h from gold.\"{table}\")").fetchone()
    return {"rows": row_count, "columns": len(columns), "hash": digest}


def fingerprints(con: duckdb.DuckDBPyConnection) -> Dict[str, dict]:
    return {t: fingerprint(con, t) for t in gold_tables(con)}


def export(con: duckdb.DuckDBPyConnection) -> None:
    GOLD.mkdir(parents=True, exist_ok=True)
    for stale in [*GOLD.glob("*.parquet"), *GOLD.glob("*.csv")]:
        stale.unlink()
    for table in gold_tables(con):
        parquet = GOLD / f"{table}.parquet"
        con.execute(f"copy (select * from gold.\"{table}\" order by all) to '{parquet.relative_to(ROOT)}' (format parquet, compression zstd)")
        rows = con.execute(f"select count(*) from gold.\"{table}\"").fetchone()[0]
        if rows <= CSV_MAX_ROWS:
            csv = GOLD / f"{table}.csv"
            con.execute(f"copy (select * from gold.\"{table}\" order by all) to '{csv.relative_to(ROOT)}' (format csv, header true)")


def main(argv: List[str]) -> int:
    con = duckdb.connect(str(WAREHOUSE.relative_to(ROOT)), read_only=True)
    export(con)
    if "--write-fingerprints" in argv:
        FINGERPRINTS.write_text(json.dumps(fingerprints(con), indent=1, sort_keys=True) + "\n")
        print(f"Wrote {FINGERPRINTS.relative_to(ROOT)}")
    print(f"Exported {len(gold_tables(con))} gold tables to {GOLD.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
