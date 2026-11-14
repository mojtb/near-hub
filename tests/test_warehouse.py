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
    return jinja2.Environment().from_string(model).render(bronze_files=lambda table: rows, explode=macros.explode, is_latest=macros.is_latest,
                                                          unix_day=macros.unix_day, yocto_to_near=macros.yocto_to_near)


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


def test_oneclick_symbol_drops_the_deprecated_mark(con):
    listed = [
        {"assetId": "nep245:v2_1.omni.hot.tg:56_2CMM", "blockchain": "bsc", "symbol": "USDT(DEPRECATED)", "decimals": 18, "price": 1},
        {"assetId": "nep141:bnb-0x55d3.omft.near", "blockchain": "bsc", "symbol": "USDT", "decimals": 18, "price": 1},
        {"assetId": "nep245:v2_1.omni.hot.tg:9745_1111", "blockchain": "plasma", "symbol": "XPL_(DEPRECATED)", "decimals": 18, "price": 0.05},
        {"assetId": "nep141:wrap.near", "blockchain": "near", "symbol": "wNEAR", "decimals": 24, "price": 4.02},
    ]
    sql = _silver("protocols/stg_oneclick__tokens.sql", [("2026-11-11", listed)])
    rows = con.execute(f"select symbol, listed_symbol, is_deprecated from ({sql}) order by asset_id").fetchall()
    assert rows == [
        ("USDT", "USDT", False),
        ("wNEAR", "wNEAR", False),
        ("USDT", "USDT(DEPRECATED)", True),
        ("XPL", "XPL_(DEPRECATED)", True),
    ]


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


LOCKUP_MACROS = (Path(__file__).resolve().parents[1] / "warehouse" / "macros" / "lockups.sql").read_text()
TRANSFERS_ENABLED_NS = 1602614338293769340.0
YEAR_NS = 365 * 86400e9


def _locked(con, t, amount=100.0, created=0.0, gone=None, withdrawn=0.0, kind="none", start=None, cliff=None, end=None, unvested=0.0,
            lockup_start=TRANSFERS_ENABLED_NS, release=None, release_end=None, changed=None, finished=None, terminating_unvested=0.0, last_kind=None, last_withdrawn=0.0, last_unvested=0.0):
    """Evaluate the gold formula for one made-up lockup."""
    body = re.search(r"{%\s*macro lockup_locked_near\(t\)\s*-?%}(.*?){%-?\s*endmacro\s*%}", LOCKUP_MACROS, re.S).group(1).replace("{{ t }}", "t")
    return con.execute(
        f"""select {body} from (select ?::double as t, ?::double as lockup_amount_near, ?::double as created_ns, ?::double as gone_ns,
                ?::double as first_withdrawn_near, ?::varchar as first_vesting_kind, ?::double as vesting_start_ns, ?::double as vesting_cliff_ns,
                ?::double as vesting_end_ns, ?::double as first_unvested_near, ?::double as lockup_start_ns, ?::double as release_duration_ns,
                ?::double as release_end_ns, ?::double as changed_ns, ?::double as finished_ns, ?::double as terminating_unvested_near,
                ?::varchar as last_vesting_kind, ?::double as last_withdrawn_near, ?::double as last_unvested_near)""",
        [t, amount, created, gone, withdrawn, kind, start, cliff, end, unvested, lockup_start, release, release_end, changed, finished, terminating_unvested, last_kind, last_withdrawn, last_unvested],
    ).fetchone()[0]


def test_lockup_holds_everything_until_its_lockup_ends_then_releases_in_a_line(con):
    start = TRANSFERS_ENABLED_NS + YEAR_NS
    plan = dict(lockup_start=start, release=4 * YEAR_NS, release_end=start + 4 * YEAR_NS)
    assert _locked(con, start - 1e12, **plan) == 100.0
    assert _locked(con, start + YEAR_NS, **plan) == pytest.approx(75.0)
    assert _locked(con, start + 4 * YEAR_NS, **plan) == 0.0


def test_early_contract_version_releases_from_transfers_enabled_not_from_the_end_of_its_lockup(con):
    # Its release runs from the day transfers were enabled, so a quarter is already out when a one-year lockup ends.
    start = TRANSFERS_ENABLED_NS + YEAR_NS
    assert _locked(con, start, lockup_start=start, release=4 * YEAR_NS, release_end=TRANSFERS_ENABLED_NS + 4 * YEAR_NS) == pytest.approx(75.0)


def test_lockup_vesting_holds_everything_before_the_cliff_and_the_larger_of_the_two_counts(con):
    plan = dict(kind="schedule", start=0.0, cliff=YEAR_NS, end=4 * YEAR_NS, lockup_start=0.0)
    assert _locked(con, YEAR_NS / 2, **plan) == 100.0
    assert _locked(con, 2 * YEAR_NS, **plan) == pytest.approx(50.0)
    assert _locked(con, 2 * YEAR_NS, **plan, release=4 * YEAR_NS, release_end=5 * YEAR_NS) == pytest.approx(75.0)


def test_lockup_termination_locks_the_unvested_amount_until_it_has_left(con):
    plan = dict(kind="schedule", start=0.0, cliff=0.0, end=4 * YEAR_NS, lockup_start=0.0, changed=YEAR_NS, finished=2 * YEAR_NS,
                terminating_unvested=75.0, last_kind="none", last_withdrawn=75.0)
    assert _locked(con, YEAR_NS - 1e12, **plan) == pytest.approx(75.0, abs=0.01)
    assert _locked(con, 1.5 * YEAR_NS, **plan) == 75.0  # the schedule alone would say 62.5
    assert _locked(con, 2 * YEAR_NS, **plan) == 0.0


def test_lockup_termination_still_open_stays_at_what_the_newest_state_says(con):
    plan = dict(kind="hash", lockup_start=0.0, changed=YEAR_NS, finished=YEAR_NS, last_kind="terminating", last_unvested=40.0)
    assert _locked(con, YEAR_NS - 1e12, **plan) == 0.0
    assert _locked(con, 10 * YEAR_NS, **plan) == 40.0


def test_lockup_counts_only_while_it_exists(con):
    assert _locked(con, TRANSFERS_ENABLED_NS - 1e12, created=TRANSFERS_ENABLED_NS) == 0.0
    assert _locked(con, TRANSFERS_ENABLED_NS, created=0.0, gone=TRANSFERS_ENABLED_NS, lockup_start=2 * TRANSFERS_ENABLED_NS) == 0.0


def test_lockup_vesting_hidden_behind_a_hash_counts_as_no_vesting(con):
    assert _locked(con, YEAR_NS, kind="hash", lockup_start=0.0) == 0.0


def test_defillama_price_is_dated_by_the_nearest_midnight(con):
    # DefiLlama stamps a daily point near the midnight that ends the day, a few seconds or up to hours either side.
    # 2026-11-02 00:00:03 closes 2026-11-01 and 2026-11-02 23:59:57 closes 2026-11-02. Taking the raw timestamp's day put
    # both on 2026-11-02 and left 2026-11-01 empty.
    midnight_nov_2 = 1793577600
    prices = [{"timestamp": midnight_nov_2 + 3, "price": 2.0}, {"timestamp": midnight_nov_2 + 86397, "price": 2.5},
              {"timestamp": midnight_nov_2 + 2 * 86400 + 5400, "price": 3.0}]
    doc = {"coins": {"coingecko:near": {"prices": prices}}}
    bronze = f"select cast('2026-11-05' as date) as snapshot_date, 'near__recent' as file_key, '{json.dumps(doc)}'::json as doc"
    macros = jinja2.Environment().from_string(MACROS).module
    model = (Path(__file__).resolve().parents[1] / "warehouse" / "models" / "silver" / "defillama" / "stg_defillama__peer_price.sql").read_text()
    sql = jinja2.Environment().from_string(model).render(bronze_files=lambda table: bronze, explode=macros.explode,
                                                         is_latest=macros.is_latest, unix_day=macros.unix_day)
    rows = con.execute(f"select cast(date_day as varchar), price_usd from ({sql}) order by 1").fetchall()
    assert rows == [("2026-11-01", 2.0), ("2026-11-02", 2.5), ("2026-11-03", 3.0)]


def test_defillama_token_price_takes_the_coin_from_the_reply_and_dates_it_by_the_nearest_midnight(con):
    # The file name cannot hold a coin key's colon, so the key is read from the reply. A stamp 49 minutes after the
    # midnight that starts 2026-09-24 closes 2026-09-23, and one seven minutes before the next midnight closes 2026-09-24.
    # A window from before the coin's first price is an empty reply and leaves no row.
    midnight_sep_24 = 1790208000
    key = "ethereum:0x0f38"
    prices = [{"timestamp": midnight_sep_24 + 2960, "price": 1.0202}, {"timestamp": midnight_sep_24 + 86400 - 500, "price": 1.0203}]
    sql = _silver("defillama/stg_defillama__token_price.sql", [
        ("2026-11-12", {"coins": {}}),
        ("2026-11-12", {"coins": {key: {"symbol": "TLO", "decimals": 8, "confidence": 0.99, "prices": prices}}}),
        ("2026-11-13", {"coins": {key: {"symbol": "TLO", "decimals": 8, "confidence": 0.99, "prices": [{"timestamp": midnight_sep_24 + 86400 - 400, "price": 1.0204}]}}}),
    ])
    rows = con.execute(f"select coin_key, listed_symbol, cast(date_day as varchar), cast(priced_at as varchar), price_usd, is_latest from ({sql}) order by date_day, snapshot_date").fetchall()
    assert rows == [(key, "TLO", "2026-09-23", "2026-09-24 00:49:20", 1.0202, True),
                    (key, "TLO", "2026-09-24", "2026-09-24 23:51:40", 1.0203, False),
                    (key, "TLO", "2026-09-24", "2026-09-24 23:53:20", 1.0204, True)]  # a later read of a day replaces the earlier one


def test_coinmetrics_token_price_dates_a_rate_by_the_day_it_closes(con):
    # CoinMetrics stamps the fixed close at 00:00 UTC as a day ends with that day's own date, so no day is moved. The
    # day a snapshot was taken on is not over yet and is left out.
    data = [{"asset": "zec", "time": "2026-11-11T00:00:00.000000000Z", "PriceUSD": "963.407991290132"},
            {"asset": "zec", "time": "2026-11-12T00:00:00.000000000Z", "PriceUSD": "949.690221828208"}]
    sql = _silver("market/stg_coinmetrics__token_price.sql", [("2026-11-12", {"data": data})])
    assert con.execute(f"select coinmetrics_asset, cast(date_day as varchar), price_usd, is_latest from ({sql})").fetchall() == [
        ("zec", "2026-11-11", 963.407991290132, True)]


def _bq_doc(rows, **head):
    return {"query": "q", "page": 0, "rows": rows, **head}


def test_bigquery_later_read_replaces_a_days_whole_list_of_receivers(con):
    # On the first read 11 November was still loading: the day total was low and a.near led. The next read has the whole
    # day, and b.near has taken a.near's place. Only the newer read's rows may count for that day, or a.near would linger.
    day = {"block_date": "2026-11-11", "signers": "5", "receivers": "9"}
    first = _bq_doc([{**day, "is_day_total": "1", "receiver_account_id": None, "txns": "100", "rank_by_txns": None, "rank_by_signers": None},
                     {**day, "is_day_total": "0", "receiver_account_id": "a.near", "txns": "60", "rank_by_txns": "1", "rank_by_signers": "1"}])
    second = _bq_doc([{**day, "is_day_total": "1", "receiver_account_id": None, "txns": "900", "rank_by_txns": None, "rank_by_signers": None},
                      {**day, "is_day_total": "0", "receiver_account_id": "b.near", "txns": "500", "rank_by_txns": "1", "rank_by_signers": "2"},
                      {"block_date": "2026-11-12", "is_day_total": "1", "receiver_account_id": None, "txns": "7", "signers": "1", "receivers": "1",
                       "rank_by_txns": None, "rank_by_signers": None}])
    sql = _silver("bigquery/stg_bigquery__transactions_daily.sql", [("2026-11-12", first), ("2026-11-13", second)])
    rows = con.execute(f"select cast(date_day as varchar), is_day_total, receiver_account_id, txns, rank_by_txns from ({sql}) where is_latest order by 1, 2 desc, 3").fetchall()
    assert rows == [("2026-11-11", True, None, 900, None), ("2026-11-11", False, "b.near", 500, 1), ("2026-11-12", True, None, 7, None)]


def test_bigquery_partition_ids_become_days_and_its_own_buckets_keep_no_day(con):
    doc = _bq_doc([{"table_name": "transactions", "partition_id": "20261111", "total_rows": "891297", "total_logical_bytes": "5", "last_modified_utc": "2026-11-12T00:41:07Z"},
                   {"table_name": "transactions", "partition_id": "__NULL__", "total_rows": "0", "total_logical_bytes": "0", "last_modified_utc": "2026-11-12T00:41:07Z"}])
    sql = _silver("bigquery/stg_bigquery__partitions.sql", [("2026-11-12", doc)])
    rows = con.execute(f"select partition_id, cast(date_day as varchar), total_rows, cast(last_modified_at as varchar) from ({sql}) order by 1").fetchall()
    assert rows == [("20261111", "2026-11-11", 891297, "2026-11-12 00:41:07"), ("__NULL__", None, 0, "2026-11-12 00:41:07")]


def test_bigquery_actions_split_day_totals_from_the_contracts_listed(con):
    base = {"block_date": "2026-11-11", "signers": "3", "predecessors": "4", "receivers": "2", "from_system": "0"}
    doc = _bq_doc([{**base, "action_kind": "FUNCTION_CALL", "is_kind_total": "1", "contract_id": None, "actions": "10", "rank_by_calls": None, "rank_by_signers": None, "rank_by_predecessors": None},
                   {**base, "action_kind": "FUNCTION_CALL", "is_kind_total": "0", "contract_id": "game.hot.tg", "actions": "8", "rank_by_calls": "1", "rank_by_signers": "1", "rank_by_predecessors": "1"},
                   {**base, "action_kind": "TRANSFER", "is_kind_total": "1", "contract_id": None, "actions": "6", "from_system": "5", "rank_by_calls": None, "rank_by_signers": None, "rank_by_predecessors": None}])
    sql = _silver("bigquery/stg_bigquery__actions_daily.sql", [("2026-11-12", doc)])
    rows = con.execute(f"select action_kind, is_kind_total, contract_id, actions, from_system, rank_by_calls from ({sql}) where is_latest order by 1, 2 desc").fetchall()
    assert rows == [("FUNCTION_CALL", True, None, 10, 0, None), ("FUNCTION_CALL", False, "game.hot.tg", 8, 0, 1), ("TRANSFER", True, None, 6, 5, None)]


def test_bigquery_cohorts_take_the_newest_read_and_the_day_it_ended(con):
    old = _bq_doc([{"cohort_month": "2026-10-01", "active_month": "2026-10-01", "signers": "10"}], parameters={"last_day": "2026-10-31"})
    new = _bq_doc([{"cohort_month": "2026-10-01", "active_month": "2026-10-01", "signers": "12"},
                   {"cohort_month": "2026-10-01", "active_month": "2026-11-01", "signers": "3"}], parameters={"last_day": "2026-11-11"})
    sql = _silver("bigquery/stg_bigquery__signer_cohorts.sql", [("2026-11-01", old), ("2026-11-12", new)])
    rows = con.execute(f"select cast(active_month as varchar), signers, cast(last_day as varchar) from ({sql}) where is_latest order by 1").fetchall()
    assert rows == [("2026-10-01", 12, "2026-11-11"), ("2026-11-01", 3, "2026-11-11")]


def test_bigquery_a_wider_read_taken_later_in_the_same_snapshot_replaces_the_first(con):
    # The first read of the snapshot kept ten receivers a day; a second read the same day kept twenty-five. Both files sit
    # in one snapshot, and the first has the greater key, so only the time of the read can say which is newer.
    day = {"block_date": "2026-11-11", "is_day_total": "0", "signers": "5", "receivers": "1", "rank_by_signers": "1"}
    first = _bq_doc([{**day, "receiver_account_id": "a.near", "txns": "60", "rank_by_txns": "1"}], read_at="2026-11-14T13:17:50+00:00")
    wider = _bq_doc([{**day, "receiver_account_id": "a.near", "txns": "60", "rank_by_txns": "1"},
                     {**day, "receiver_account_id": "k.near", "txns": "3", "rank_by_txns": "11"}], read_at="2026-11-14T13:45:00+00:00")
    model = (Path(__file__).resolve().parents[1] / "warehouse" / "models" / "silver" / "bigquery" / "stg_bigquery__transactions_daily.sql").read_text()
    macros = jinja2.Environment().from_string(MACROS).module
    files = " union all ".join(f"select cast('2026-11-12' as date) as snapshot_date, '{key}' as file_key, '{json.dumps(doc)}'::json as doc"
                               for key, doc in (("2025-11-01__2026-11-11__p000", first), ("2025-01-01__2026-11-11__p000", wider)))
    sql = jinja2.Environment().from_string(model).render(bronze_files=lambda table: files, explode=macros.explode)
    rows = con.execute(f"select read_key, receiver_account_id from ({sql}) where is_latest order by 2").fetchall()
    assert rows == [("2025-01-01__2026-11-11", "a.near"), ("2025-01-01__2026-11-11", "k.near")]
