"""Tests of the SQL helpers, run in memory against small JSON files, so they need no warehouse build."""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import duckdb
import pytest

MACROS = (Path(__file__).resolve().parents[1] / "warehouse" / "macros" / "bronze.sql").read_text()


def _macro(name: str, **args: str) -> str:
    """Render one of the simple one-expression macros by substituting its Jinja arguments."""
    body = re.search(r"{%\s*macro " + name + r"\(.*?\)\s*-?%}(.*?){%-?\s*endmacro\s*%}", MACROS, re.S).group(1)
    for key, value in args.items():
        body = body.replace("{{ " + key + " }}", value)
    return body.strip()


@pytest.fixture
def con():
    return duckdb.connect()


def test_yocto_conversion_keeps_precision_beyond_a_double(con):
    expr = _macro("yocto_to_near", text_expr="'1310472976202214000000000000000001'")
    assert float(con.execute(f"select {expr}").fetchone()[0]) == pytest.approx(1310472976.202214, abs=1e-6)


def test_yocto_conversion_ignores_a_decimal_tail(con):
    expr = _macro("yocto_to_near", text_expr="'3313030900218044571800000000.000000'")
    assert float(con.execute(f"select {expr}").fetchone()[0]) == pytest.approx(3313.030900, abs=1e-5)


def test_reading_bronze_keeps_big_numbers_as_text(con, tmp_path):
    path = tmp_path / "x.json.gz"
    big = "1310472976202214000000000000000001"
    path.write_bytes(gzip.compress(json.dumps({"data": [{"amount": big}]}).encode()))
    row = con.execute(
        f"select unnest(from_json(json->'data', '[\"JSON\"]'))->>'amount' from read_json_objects('{path}', format='unstructured')"
    ).fetchone()
    assert row[0] == big


def test_unix_day_uses_utc(con):
    # 2026-11-01 00:00:00 UTC, whatever the machine's time zone
    expr = _macro("unix_day", expr="1793491200")
    assert str(con.execute(f"select {expr}").fetchone()[0]) == "2026-11-01"
