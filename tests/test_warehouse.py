"""Tests of the SQL helpers, run in memory against small JSON files, so they need no warehouse build."""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

import duckdb
import jinja2
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


def _silver(path: str, files: list) -> str:
    """A silver model's SQL, reading these (snapshot date, document) pairs instead of bronze files."""
    macros = jinja2.Environment().from_string(MACROS).module
    rows = " union all ".join(f"select cast('{day}' as date) as snapshot_date, 'all' as file_key, '{json.dumps(doc)}'::json as doc" for day, doc in files)
    model = (Path(__file__).resolve().parents[1] / "warehouse" / "models" / "silver" / path).read_text()
    return jinja2.Environment().from_string(model).render(bronze_files=lambda table: rows, explode=macros.explode, is_latest=macros.is_latest)


def test_oneclick_asset_id_names_the_near_contract(con):
    listed = [
        {"assetId": "nep141:wrap.near", "blockchain": "near", "contractAddress": "wrap.near", "decimals": 24, "price": 4.02, "priceUpdatedAt": "2026-11-05T08:02:30.896Z"},
        {"assetId": "1cs_v1:near:nep141:zec.omft.near", "blockchain": "near", "contractAddress": "zec.omft.near", "decimals": 8, "price": 1316.39, "priceUpdatedAt": "2026-11-05T08:02:30.896Z"},
        # Listed under Ethereum with a 0x address, but this is the NEAR contract that intents.near holds.
        {"assetId": "nep141:eth-0xa0b8.omft.near", "blockchain": "eth", "contractAddress": "0xa0b8", "decimals": 6, "price": 1, "priceUpdatedAt": "2026-11-05T08:02:30.896Z"},
        {"assetId": "nep245:v2_1.omni.hot.tg:10_111", "blockchain": "op", "decimals": 18, "price": 2413, "priceUpdatedAt": "2026-11-05T08:02:30.896Z"},
        {"assetId": "1cs_v1:aptos:aptos-fa:0x09", "blockchain": "aptos", "contractAddress": "0x09", "decimals": 8, "price": 1, "priceUpdatedAt": "2026-11-02T16:16:30.932Z"},
    ]
    sql = _silver("protocols/stg_oneclick__tokens.sql", [("2026-11-05", listed)])
    rows = con.execute(f"select asset_id, near_token_id, cast(price_date as varchar) from ({sql})").fetchall()
    assert sorted(rows) == sorted([
        ("nep141:wrap.near", "wrap.near", "2026-11-05"),
        ("1cs_v1:near:nep141:zec.omft.near", "zec.omft.near", "2026-11-05"),
        ("nep141:eth-0xa0b8.omft.near", "eth-0xa0b8.omft.near", "2026-11-05"),
        ("nep245:v2_1.omni.hot.tg:10_111", None, "2026-11-05"),
        ("1cs_v1:aptos:aptos-fa:0x09", None, "2026-11-02"),
    ])


def test_rhea_price_keeps_the_first_read_of_that_exact_price(con):
    files = [
        ("2026-11-01", {"same.near": {"price": "0.5", "symbol": "", "decimal": 18}, "moved.near": {"price": "1.0000000000000000000000000001", "symbol": "USDC", "decimal": 6}}),
        # These two prices are one double, so only the text shows the change.
        ("2026-11-02", {"same.near": {"price": "0.5", "symbol": "", "decimal": 18}, "moved.near": {"price": "1.0000000000000000000000000002", "symbol": "USDC", "decimal": 6}}),
        ("2026-11-03", {"same.near": {"price": "0.5", "symbol": "", "decimal": 18}, "moved.near": {"price": "1.0000000000000000000000000002", "symbol": "USDC", "decimal": 6}}),
    ]
    sql = _silver("protocols/stg_rhea__token_prices.sql", files)
    rows = con.execute(f"select token_id, cast(snapshot_date as varchar), cast(price_first_read as varchar), is_latest from ({sql}) order by 1, 2").fetchall()
    assert rows == [
        ("moved.near", "2026-11-01", "2026-11-01", False),
        ("moved.near", "2026-11-02", "2026-11-02", False),
        ("moved.near", "2026-11-03", "2026-11-02", True),
        ("same.near", "2026-11-01", "2026-11-01", False),
        ("same.near", "2026-11-02", "2026-11-01", False),
        ("same.near", "2026-11-03", "2026-11-01", True),
    ]


def test_rhea_price_that_is_not_a_number_is_no_price(con):
    sql = _silver("protocols/stg_rhea__token_prices.sql", [("2026-11-05", {"bad.near": {"price": "N/A", "symbol": "BAD", "decimal": 6}})])
    assert con.execute(f"select token_id, symbol, decimals, price_usd from ({sql})").fetchall() == [("bad.near", "BAD", 6, None)]


def test_rhea_pools_become_one_row_per_token(con):
    pools = [
        {"id": "1", "pool_kind": "SIMPLE_POOL", "token_account_ids": ["wrap.near", "a.near"], "amounts": ["100", "200"]},
        {"id": "2", "pool_kind": "RATED_SWAP", "token_account_ids": ["b.near", "c.near", "d.near"], "amounts": ["1", "2", "3"]},
    ]
    sql = _silver("protocols/stg_rhea__pool_legs.sql", [("2026-11-05", pools)])
    rows = con.execute(f"select pool_id, token_id, amount_raw from ({sql}) order by 1, 2").fetchall()
    assert rows == [("1", "a.near", "200"), ("1", "wrap.near", "100"), ("2", "b.near", "1"), ("2", "c.near", "2"), ("2", "d.near", "3")]
