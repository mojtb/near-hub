"""Generate docs/DATA_CATALOG.md, docs/RECONCILIATION.md, data/gold/_catalog.json and the README's expected
results from the built warehouse.

Descriptions, grains and units come from warehouse/models/gold/_gold.yml, read through dbt's manifest, so
the catalog can never drift from the tables it describes. Run `make catalog` after `make warehouse`.
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
AREAS = [
    ("Calendar and registry", ["dim_date", "dim_entity", "dim_token", "dim_event", "dim_block_day", "dim_protocol", "dim_source"]),
    ("Chain usage, supply and parameters", ["fct_chain_daily", "fct_supply_daily", "fct_circulating_supply_daily", "fct_protocol_config", "fct_contract_daily", "fct_receiver_sample_daily"]),
    ("NEAR Intents and revenue", ["fct_intents_daily", "fct_intents_chain_daily", "fct_intents_asset_daily", "fct_intents_fee_channels",
                                  "fct_intents_dashboard_readings", "fct_dune_intents_asset_daily", "fct_dune_intents_chain_daily", "fct_dune_intents_swaps_daily",
                                  "fct_dune_intents_tvl_daily", "fct_dune_intents_tvl_asset_daily", "fct_intents_pool_chain_monthly", "fct_dune_dashboard_results",
                                  "fct_intents_1click_daily", "fct_intents_1click_channel_daily", "fct_intents_1click_pair_daily", "fct_intents_1click_route_daily", "fct_intents_1click_size_daily",
                                  "fct_intents_1click_fee_recipient_daily", "fct_revenue_capture", "fct_revenue_page_emissions", "fct_revenue_page_monthly"]),
    ("Wallets", ["fct_wallet_transfers", "fct_wallet_flows_daily", "fct_wallet_counterparties", "fct_revenue_inflows_daily", "fct_wallet_balance_daily", "fct_wallet_holdings", "fct_token_holders"]),
    ("Security and staking", ["fct_validator_epoch", "fct_validator_summary", "fct_chain_signatures_daily", "fct_mpc_state", "fct_mpc_participants", "fct_mpc_operators", "fct_lst_snapshot"]),
    ("Capital and DeFi", ["fct_protocol_tvl_daily", "fct_defi_tvl_daily", "fct_exchange_balance_daily", "fct_protocol_fees_snapshot", "fct_stablecoin_assets", "fct_yield_pools"]),
    ("Market and peers", ["fct_market_daily", "fct_token_prices", "fct_token_price_daily", "fct_peer_daily", "fct_peer_supply_readings", "fct_peer_app_fees_snapshot",
                          "fct_peer_chain_fees_snapshot", "fct_swap_services_daily", "fct_etf_nrr_daily", "fct_etf_nrr_chain_daily"]),
    ("Developers and governance", ["fct_dev_activity_weekly", "fct_repo_snapshot", "fct_catalog_projects", "fct_governance_threads", "fct_governance_proposals", "fct_governance_decisions",
                                   "fct_venear_snapshot"]),
    ("Thesis models", ["fct_thesis_scorecard", "dim_claim", "fct_net_dilution_daily", "fct_deflation_scenarios",
                       "fct_intents_unit_economics_monthly", "fct_intents_channel_economics_monthly", "fct_intents_concentration_monthly",
                       "fct_valuation_multiples_daily", "fct_usage_quality_daily", "fct_usage_lead_correlations",
                       "fct_etf_absorption_daily"]),
    ("Data quality", ["dq_reconciliation", "dq_freshness", "dq_revisions", "dq_ingest_runs", "dq_provenance"]),
]
DATE_COLUMNS = ("date_day", "snapshot_date", "week_start", "month_start", "event_date")


def _cell(value: Any) -> str:
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _table_facts(con: duckdb.DuckDBPyConnection, table: str, columns: List[str]) -> Dict[str, Any]:
    rows = con.execute(f'select count(*) from gold."{table}"').fetchone()[0]
    facts: Dict[str, Any] = {"rows": rows, "first": None, "last": None}
    for column in DATE_COLUMNS:
        if column in columns:
            first, last = con.execute(f'select min("{column}"), max("{column}") from gold."{table}"').fetchone()
            facts.update(first=str(first) if first else None, last=str(last) if last else None)
            break
    return facts


def build_catalog(con: duckdb.DuckDBPyConnection) -> List[Dict[str, Any]]:
    manifest = json.loads((ROOT / "warehouse" / "target" / "manifest.json").read_text())
    nodes = {n["name"]: n for n in manifest["nodes"].values() if n["resource_type"] == "model" and n["schema"] == "gold"}
    types = {}
    for table, column, data_type in con.execute("select table_name, column_name, data_type from information_schema.columns where table_schema = 'gold' order by ordinal_position").fetchall():
        types.setdefault(table, []).append((column, data_type))
    uncatalogued = set(types) - {t for _, tables in AREAS for t in tables}
    if uncatalogued:
        raise SystemExit(f"Gold tables missing from AREAS in tools/catalog.py: {sorted(uncatalogued)}")
    catalog = []
    for area, tables in AREAS:
        for table in tables:
            node = nodes[table]
            meta = node.get("meta") or node.get("config", {}).get("meta", {})
            columns = []
            for column, data_type in types[table]:
                doc = node["columns"].get(column, {})
                unit = (doc.get("meta") or doc.get("config", {}).get("meta", {})).get("unit", "")
                columns.append({"name": column, "type": data_type, "unit": unit, "description": doc.get("description", "")})
            facts = _table_facts(con, table, [c["name"] for c in columns])
            catalog.append({"area": area, "table": table, "description": node.get("description", ""), "grain": meta.get("grain", ""),
                            "sources": meta.get("sources", ""), "path": f"data/gold/{table}.parquet", "columns": columns, **facts})
    return catalog


def write_catalog(catalog: List[Dict[str, Any]]) -> None:
    lines = ["# Data catalog", "",
             "Generated by `make catalog`. Do not edit by hand: descriptions live in `warehouse/models/gold/_gold.yml`.", "",
             f"{len(catalog)} gold tables and {sum(len(t['columns']) for t in catalog)} columns. Every table is in `data/gold/` as Parquet.", ""]
    for area, _ in AREAS:
        lines += [f"## {area}", "", "| Table | Rows | Dates | Grain |", "|---|---|---|---|"]
        for t in [t for t in catalog if t["area"] == area]:
            dates = f"{t['first']} to {t['last']}" if t["first"] else ""
            lines.append(f"| [`{t['table']}`](#{t['table']}) | {t['rows']:,} | {dates} | {_cell(t['grain'])} |")
        lines.append("")
    for t in catalog:
        lines += [f"### {t['table']}", "", t["description"], "", f"- **Grain:** {t['grain']}", f"- **Sources:** {t['sources']}", f"- **File:** `{t['path']}`", "",
                  "| Column | Type | Unit | Description |", "|---|---|---|---|"]
        lines += [f"| `{c['name']}` | {c['type']} | {_cell(c['unit'])} | {_cell(c['description'])} |" for c in t["columns"]]
        lines.append("")
    (DOCS / "DATA_CATALOG.md").write_text("\n".join(lines))


def _number(value: Any) -> str:
    if value is None:
        return ""
    return f"{value:,.4f}" if abs(value) < 100 else f"{value:,.0f}"


def write_reconciliation(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute("""
        select check_id, metric, subject, source_a, value_a, source_b, value_b, diff_pct, tolerance_pct, independence, status, explanation
        from gold.dq_reconciliation order by case status when 'differs' then 0 when 'not_available' then 1 else 2 end, check_id, subject""").fetchall()
    as_of = con.execute("select max(as_of) from gold.dq_freshness").fetchone()[0]
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r[10]] = counts.get(r[10], 0) + 1
    independent = sum(1 for r in rows if r[9] == "independent" and r[10] == "agree")
    lines = ["# Reconciliation report", "", f"Generated by `make catalog` from `gold.dq_reconciliation`, using data through {as_of}.", "",
             f"{len(rows)} comparisons: {counts.get('agree', 0)} agree, {counts.get('differs', 0)} differ, {counts.get('not_available', 0)} not available. "
             f"{independent} of the agreements are between independent sources. The others share an upstream, usually NEAR's Dune uploads, so they prove less.", "",
             "| Status | Check | Subject | Source A | Value A | Source B | Value B | Gap % | Tolerance % | Independence |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        gap = f"{r[7]:.3f}" if r[7] is not None else ""
        lines.append(f"| {r[10]} | `{r[0]}` | {_cell(r[2])} | {_cell(r[3])} | {_number(r[4])} | {_cell(r[5])} | {_number(r[6])} | {gap} | {r[8]:g} | {r[9]} |")
    explained = [r for r in rows if r[10] == "differs"]
    lines += ["", "## Why the gaps exist", ""]
    lines += [f"- **`{r[0]}`**: {r[11] or 'not explained yet'}" for r in explained] or ["No gaps beyond tolerance."]
    (DOCS / "RECONCILIATION.md").write_text("\n".join(lines) + "\n")


def expected_results(con: duckdb.DuckDBPyConnection) -> str:
    """The README block that `make verify` holds to the warehouse. Each line is a question with its answer."""
    one = lambda sql: con.execute(sql).fetchone()
    tables, columns = one("select count(distinct table_name), count(*) from information_schema.columns where table_schema = 'gold'")
    as_of, last_day = one("select max(as_of), mode(latest_data_day) from gold.dq_freshness")
    dune_day = one("select max(snapshot_date) - 1 from gold.fct_intents_dashboard_readings")[0]
    agree, differ = one("select count(*) filter (where status = 'agree'), count(*) filter (where status = 'differs') from gold.dq_reconciliation")
    minted, config = one("select value_a, value_b from gold.dq_reconciliation where check_id = 'issuance_rate_30d_minted_vs_config'")
    llama, wallets = one("select value_a, value_b from gold.dq_reconciliation where check_id = 'intents_revenue_all_time_defillama_vs_wallets'")
    nb, dune = one("select value_a, value_b from gold.dq_reconciliation where check_id = 'intents_volume_all_time_nearblocks_vs_dune_public'")
    participants, threshold = one("select participants, threshold from gold.fct_mpc_state order by snapshot_date desc limit 1")
    channel, share, channel_read = one("select referral, share_of_listed_fees, snapshot_date from gold.fct_intents_fee_channels order by snapshot_date desc, channel_rank limit 1")
    chain_shares, fund_shares = one("select value_a, value_b from gold.dq_reconciliation where check_id = 'etf_nrr_shares_chain_vs_fund'")
    circulating, circulating_share = one("select circulating_supply_near, circulating_share_of_total from gold.fct_circulating_supply_daily order by date_day desc limit 1")
    live_chain, live_nearblocks = one("select value_a, value_b from gold.dq_reconciliation where check_id = 'circulating_supply_last_live_day_chain_vs_nearblocks'")
    lines = [
        f"- Data through: **{last_day}**, the last full UTC day before the pinned snapshot of {as_of}; `dq_freshness` lists any source that ends earlier",
        f"- Gold tables and columns: **{tables}** and **{columns}**",
        f"- Reconciliation: **{agree}** comparisons agree, **{differ}** differ, each with a written explanation",
        f"- Issuance over the last 30 days, from supply change plus burn: **{minted * 100:.2f}%** a year, against **{config * 100:.2f}%** in the protocol config",
        f"- Circulating supply, built from NEAR's lockup contracts: **{circulating / 1e6:,.2f}M** NEAR, **{circulating_share * 100:.2f}%** of total supply; on 2025-08-26, the last day NearBlocks computed its own, **{live_chain / 1e6:,.2f}M** against **{live_nearblocks / 1e6:,.2f}M**",
        f"- Captured Intents revenue, all time: **${llama / 1e6:.2f}M** per DefiLlama, **${wallets / 1e6:.2f}M** rebuilt from wallet transfers",
        f"- Public Intents volume, all time through {dune_day}, the last full day of the latest Dune reading: **${nb / 1e9:.2f}B** per NearBlocks, **${dune / 1e9:.2f}B** per NEAR's dashboard on Dune",
        f"- Chain Signatures: **{participants}** MPC participants with a threshold of **{threshold}**",
        f"- Largest Intents fee channel, per NEAR's dashboard on Dune as read on {channel_read}: **{channel}**, with **{share * 100:.0f}%** of listed fees",
        f"- Bitwise NEAR ETF shares outstanding: **{fund_shares:,.0f}** per the fund, **{chain_shares:,.0f}** counted on chain in whole baskets",
    ]
    return "\n".join(lines)


def verdict(con: duckdb.DuckDBPyConnection) -> str:
    """The README's headline result, so the first thing a reader sees cannot drift from the scorecard."""
    one = lambda sql: con.execute(sql).fetchone()
    # A claim for the case supports it when it holds; a claim naming a risk supports it when it fails.
    stands = """count(*) filter (where (side = 'bull') = (status = 'holds') and status <> 'not_testable')"""
    against = """count(*) filter (where (side = 'bull') <> (status = 'holds') and status <> 'not_testable')"""
    no_test = "count(*) filter (where status = 'not_testable')"
    f, a, n, day = one(f"select {stands}, {against}, {no_test}, max(as_of_date) from gold.fct_thesis_scorecard")
    # The 30 days to the newest day whose fees have settled, which is the window THESIS.md and the dashboard read.
    off = one("""select offset_share, date_day from gold.fct_net_dilution_daily
                 where date_day = (select max(date_day) from gold.fct_intents_daily
                                   where not is_fee_revenue_provisional)""")
    return (f"**Where the case stands at the snapshot of {day}:** of {f + a} claims the data can test, "
            f"**{f}** support the long case and **{a}** count against it; **{n}** more cannot be tested from public "
            f"data. Over the 30 days to {off[1]}, fees reaching NEAR's revenue wallets and gas burned offset "
            f"**{off[0] * 100:.1f}%** of the new NEAR the chain created.")


def source_table(con: duckdb.DuckDBPyConnection) -> str:
    """The data notice's table of sources, generated from registry/sources.csv so the notice cannot drift from it."""
    rows = con.execute("""
        select source, provides, terms_summary, terms_url
        from gold.dim_source
        where provides is not null and lower(provides) not like 'not used%'
        order by source""").fetchall()
    cell = lambda v: (v or "").replace("|", "\\|").replace("\n", " ").strip()
    lines = ["| Source | What it gives this project | Its terms, as read when it was added | Terms page |", "|---|---|---|---|"]
    for source, provides, terms, url in rows:
        link = f"[{cell(url).split('//')[-1].split('/')[0]}]({cell(url)})" if url else "none found"
        lines.append(f"| `{cell(source)}` | {cell(provides)} | {cell(terms)} | {link} |")
    return "\n".join(lines)


def _splice(path: Path, name: str, body: str) -> None:
    """Replace what sits between <!-- name:start --> and <!-- name:end --> in a file that is otherwise written by hand."""
    text = path.read_text()
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    path.write_text(f"{before}{start}\n{body}\n{end}{after}")


def write_readme_results(con: duckdb.DuckDBPyConnection) -> None:
    _splice(ROOT / "README.md", "verdict", verdict(con))
    _splice(ROOT / "README.md", "expected", expected_results(con))


def write_data_notice(con: duckdb.DuckDBPyConnection) -> None:
    _splice(ROOT / "DATA_NOTICE.md", "sources", source_table(con))


def main() -> None:
    os.chdir(ROOT)
    DOCS.mkdir(exist_ok=True)
    con = duckdb.connect("data/warehouse.duckdb", read_only=True)
    catalog = build_catalog(con)
    write_catalog(catalog)
    write_reconciliation(con)
    write_readme_results(con)
    write_data_notice(con)
    (ROOT / "data" / "gold" / "_catalog.json").write_text(json.dumps(catalog, indent=1) + "\n")
    print(f"Wrote docs/DATA_CATALOG.md, docs/RECONCILIATION.md, DATA_NOTICE.md's source table "
          f"and data/gold/_catalog.json ({len(catalog)} tables)")


if __name__ == "__main__":
    main()
