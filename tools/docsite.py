"""Generate site/docs/index.html: a browsable guide to every gold table, its fields, and how much history it holds.
It sits inside the dashboard's folder, so the dashboard links to it and both are served together.

Descriptions, grains and units come from warehouse/models/gold/_gold.yml through tools.catalog. Coverage is measured
in the built warehouse, and backfill progress is read from data/state and the fetchers' own settings, so the site is
rebuilt from the data, never edited by hand. Run it after `make warehouse catalog`:

    .venv/bin/python -m tools.docsite                      # writes site/docs/index.html (`make docs` does this)
    .venv/bin/python -m tools.docsite --fragment out.html  # also writes the page without its document wrapper
"""
from __future__ import annotations

import argparse
from bisect import bisect_left, bisect_right
import json
import math
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import duckdb

from ingest.sources import defillama, ecosystem, fastnear, intents, neardata, rpc
from tools.catalog import AREAS, build_catalog

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "data" / "state"
TEMPLATE = Path(__file__).with_name("docsite_template.html")
OUT = ROOT / "site" / "docs" / "index.html"
HUB = ROOT / "site"  # the dashboard this guide is a companion to; the guide links back to it
# What a link to the guide shows when it is shared. A share card needs full addresses, so the site's own is written
# here. The card is the dashboard's, site/share-card.png.
SITE_URL = "https://nearhub.tech"
SHARE_TEXT = ("The finished tables behind NEAR Hub and their fields: what each one measures, where it comes from, "
              "and how much history is in.")
SHARE_TAGS = (f'<meta name="description" content="{SHARE_TEXT}">\n'
              '<meta property="og:type" content="website">\n'
              '<meta property="og:site_name" content="NEAR Hub">\n'
              '<meta property="og:title" content="NEAR Hub Docs: a guide to every table and field">\n'
              f'<meta property="og:description" content="{SHARE_TEXT}">\n'
              f'<meta property="og:url" content="{SITE_URL}/docs/">\n'
              f'<meta property="og:image" content="{SITE_URL}/share-card.png">\n'
              '<meta property="og:image:width" content="1200">\n'
              '<meta property="og:image:height" content="630">\n'
              '<meta property="og:image:alt" content="NEAR Hub: an investment case for NEAR, tested claim by claim. '
              'The case, as five links.">\n'
              '<meta name="twitter:card" content="summary_large_image">\n')
EPOCH = date(1970, 1, 1)
DATE_COLUMNS = ("date_day", "snapshot_date", "week_start", "month_start", "event_date")
RECEIVER_WINDOW_DAYS = 365  # the window ingest/sources/neardata.py backfills

KINDS = [
    {"id": "full", "label": "Full history", "short": "Full", "blurb": "Complete: all the history the source has, or all the warehouse is built to read, is in."},
    {"id": "backfill", "label": "Backfilling", "short": "Backfilling", "blurb": "Older history exists, and a nightly job fetches it a batch at a time."},
    {"id": "window", "label": "Rolling window", "short": "Window", "blurb": "Only a recent window is read, because the source serves no more or the fetcher asks for no more. History starts there and grows forward."},
    {"id": "snapshot", "label": "Snapshots", "short": "Snapshots", "blurb": "Point in time. Each nightly read adds one reading, and the past cannot be read back."},
    {"id": "hand", "label": "Read on request", "short": "On request", "blurb": "Read in a browser on request, never on a schedule. It grows only when someone reads the source again."},
    {"id": "reference", "label": "Reference", "short": "Reference", "blurb": "Registries, lists and checks with no time axis."},
]

# How each table's history behaves, and why. `cadence` says how its dates count as coverage:
# daily (each day present), weekly or monthly (each period covers its days), snapshot (each read day),
# trading (weekdays, so weekends between trading days are not gaps), event (rows only on active days, so every day
# from the first row to the latest data day counts), blockday (one block a month, then one a day: a block is a point
# sample, so only the days that hold one count; the contract views replayed at those blocks use it too, with
# `unit` naming what they are counted in). `job` links a backfill: while it has days queued the table is a backfill,
# and once it has none the table takes `done_kind` and `done_why`. `date` names a date column the default list lacks.
# Placeholders in `why` are filled from the measured tables, the job state and the fetchers' settings, so a sentence
# never repeats a number by hand: see `facts` in Site.build. {c[column]} is the first day a column has a value.
HISTORY: Dict[str, Dict[str, str]] = {
    "dim_date": {"kind": "full", "cadence": "daily", "why": "The calendar spine: every day from {first}{spine_note} to {last}."},
    "dim_entity": {"kind": "reference", "why": "The reviewed wallet and contract registry. Each label carries its own evidence and source."},
    "dim_token": {"kind": "reference", "why": "Registry tokens with their decimals."},
    "dim_event": {"kind": "reference", "why": "Dated events, curated by hand and added as they happen, from {first} to {last}."},
    "dim_block_day": {"kind": "full", "cadence": "blockday", "why": "A lookup of block heights: the first block of each month from {monthly_from}, and of each day from {daily_from}, by design. {block_note}"},
    "dim_protocol": {"kind": "reference", "why": "Protocols DefiLlama lists on NEAR, as of their newest reading."},
    "dim_source": {"kind": "reference", "why": "Every source with its access, limits and terms."},
    "fct_chain_daily": {"kind": "full", "cadence": "daily", "why": "Every day since {first}, from NearBlocks /v1/charts for older days and /v3 for the last year. {late_cols} columns exist only in /v3, which serves the last 365 days, so they start {late_from}. {ending_cols} columns come only from /v1 and end on {ends_on}, when NearBlocks switches /v1 off."},
    "fct_supply_daily": {"kind": "full", "cadence": "daily", "why": "Every day since {first}."},
    "fct_circulating_supply_daily": {"kind": "full", "cadence": "daily", "why": "Every day since {first}, when transfers were enabled. Nothing circulated before."},
    "fct_protocol_config": {"kind": "snapshot", "cadence": "snapshot", "why": "The RPC returns today's parameters only, so each nightly read adds one row. {readings} Earlier changes are dated in registry/protocol_upgrades.csv."},
    "fct_contract_daily": {"kind": "window", "cadence": "event", "why": "NearBlocks returns each contract's last 365 active days, so each contract starts where its first read reached: {first} for the oldest, {series_newest} for the newest. Rows exist only on days with activity, and history grows one day a night."},
    "fct_receiver_sample_daily": {"kind": "backfill", "cadence": "daily", "job": "receiver", "why": "Estimated from evenly spaced Neardata blocks: {blocks_new} a day for each new day, {blocks_old} a day for past days. The backfill fills a rolling {receiver_window}-day window, {receiver_pace} days a night.", "done_kind": "window", "done_why": "Estimated from evenly spaced Neardata blocks: {blocks_new} a day for each new day, and {blocks_old} a day for the {receiver_window} days before the first run, which are all in. History starts on {first}, the edge of that window, and grows one day a night. Older days are not fetched."},
    "fct_intents_daily": {"kind": "full", "cadence": "daily", "why": "Every day since the first Intents volume on {first}. The public_ columns come from NearBlocks /v3, which serves the last 365 days, so they start on {c[public_volume_usd]}. Fees start on {c[fees_usd]} and revenue on {c[revenue_usd]}, the first days their sources report."},
    "fct_intents_chain_daily": {"kind": "window", "cadence": "daily", "why": "NearBlocks /v3 serves the last 365 days, so history starts on {first} and grows one day a night. Older days are not available from this source."},
    "fct_intents_asset_daily": {"kind": "window", "cadence": "daily", "why": "NearBlocks /v3 serves the last 365 days, so history starts on {first} and grows one day a night. Older days are not available from this source."},
    "fct_intents_fee_channels": {"kind": "hand", "cadence": "snapshot", "job": "dune", "why": "Read in a browser on request from NEAR's dashboard on Dune, never on a schedule. {readings}"},
    "fct_intents_dashboard_readings": {"kind": "hand", "cadence": "snapshot", "job": "dune", "why": "The headline tiles of NEAR's dashboard on Dune, read in a browser on request. {readings}"},
    "fct_intents_pool_chain_monthly": {"kind": "full", "cadence": "event", "why": "intents.near's wNEAR, dollar tokens and the tokens of its other main assets, read from the token contracts at the first block after the last day of each month from {first_month}, and after the newest day read. Rows exist only on those days. The contract was deployed in November 2024, so there is no earlier month, and a past block stays readable, so a month missed on one night is read on a later one, and a token that joins the list is read back to its first month."},
    "fct_dune_intents_asset_daily": {"kind": "hand", "cadence": "daily", "job": "dune", "why": "Taken from the newest reading of NEAR's dashboard on Dune, which carries the whole series: {first} to {last}. The dashboard is read in a browser on request, so the table grows only when it is read again."},
    "fct_dune_intents_chain_daily": {"kind": "hand", "cadence": "daily", "job": "dune", "why": "Taken from the newest reading of NEAR's dashboard on Dune, which carries the whole series: {first} to {last}. The dashboard is read in a browser on request, so the table grows only when it is read again."},
    "fct_dune_intents_swaps_daily": {"kind": "hand", "cadence": "daily", "job": "dune", "why": "Taken from the newest reading of NEAR's dashboard on Dune, which carries the whole series: {first} to {last}. The dashboard is read in a browser on request, so the table grows only when it is read again."},
    "fct_dune_intents_tvl_daily": {"kind": "hand", "cadence": "daily", "job": "dune", "why": "Taken from the newest reading of NEAR's dashboard on Dune, which carries the whole series: {first} to {last}. The dashboard is read in a browser on request, so the table grows only when it is read again. Public balances start on {first} and confidential ones on {series_newest}."},
    "fct_dune_intents_tvl_asset_daily": {"kind": "hand", "cadence": "daily", "job": "dune", "why": "Taken from the newest reading of NEAR's dashboard on Dune, which carries the whole series: {first} to {last}. The dashboard is read in a browser on request, so the table grows only when it is read again."},
    "fct_dune_dashboard_results": {"kind": "hand", "cadence": "snapshot", "job": "dune", "why": "Every row of every widget of NEAR's dashboard on Dune read so far, in a browser on request. {readings} Reads through Dune's API start once a DUNE_API_KEY is set."},
    "fct_intents_1click_daily": {"kind": "backfill", "cadence": "daily", "job": "explorer", "why": "Tallied day by day from the Intents Explorer API. Each night walks {explorer_pages} pages: the last {explorer_full} days first, then one day a week back to {explorer_from}, then the days between.", "done_kind": "full", "done_why": "Tallied day by day from the Intents Explorer API, and complete: every day since {explorer_from} has been walked, and the first swap is on {first}. A day with no swap has no row. {explorer_empty} The last {explorer_recent} days are tallied again each night, because a swap's status can still change."},
    "fct_intents_1click_channel_daily": {"kind": "backfill", "cadence": "daily", "job": "explorer", "why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, so it fills at the same pace.", "done_kind": "full", "done_why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, which are complete from the first swap on {first}. A day with no swap has no row."},
    "fct_intents_1click_pair_daily": {"kind": "backfill", "cadence": "daily", "job": "explorer", "why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, so it fills at the same pace.", "done_kind": "full", "done_why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, which are complete from the first swap on {first}. A day with no swap has no row."},
    "fct_intents_1click_route_daily": {"kind": "backfill", "cadence": "daily", "job": "explorer", "why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, so it fills at the same pace.", "done_kind": "full", "done_why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, which are complete from the first swap on {first}. A day with no swap has no row."},
    "fct_intents_1click_size_daily": {"kind": "backfill", "cadence": "daily", "job": "explorer", "why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, so it fills at the same pace.", "done_kind": "full", "done_why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, which are complete from the first swap on {first}. A day with no swap has no row."},
    "fct_intents_1click_fee_recipient_daily": {"kind": "backfill", "cadence": "daily", "job": "explorer", "why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily. App fees first appear on {first}.", "done_kind": "full", "done_why": "Built from the same Intents Explorer day tallies as fct_intents_1click_daily, which are complete. App fees first appear on {first}; a day with none has no row."},
    "fct_revenue_capture": {"kind": "snapshot", "cadence": "snapshot", "why": "revenue.near.org shows current shares only, so each nightly read adds one reading. {readings}"},
    "fct_revenue_page_emissions": {"kind": "full", "cadence": "daily", "why": "The page's year-to-date series starts on {first}, and all of it is in."},
    "fct_revenue_page_monthly": {"kind": "full", "cadence": "monthly", "why": "NEAR's monthly revenue series from its first month, {first_month}, to {last_month}, the month in progress at the pin."},
    "fct_wallet_transfers": {"kind": "full", "cadence": "event", "why": "Every transfer of each crawled wallet, back to its first. {crawl_note}"},
    "fct_wallet_flows_daily": {"kind": "full", "cadence": "event", "why": "Summed from fct_wallet_transfers, so each wallet starts at its first transfer. Days without a transfer have no row."},
    "fct_wallet_counterparties": {"kind": "reference", "why": "A summary over all transfers, with no time axis."},
    "fct_revenue_inflows_daily": {"kind": "full", "cadence": "event", "why": "Rebuilt from wallet transfers since the first revenue inflow on {first}. Days without inflows have no row."},
    "fct_wallet_balance_daily": {"kind": "full", "cadence": "daily", "why": "Every day since each wallet's first transfer, carried forward over days without one. The oldest wallet starts on {first} and the newest on {series_newest}."},
    "fct_wallet_holdings": {"kind": "snapshot", "cadence": "snapshot", "why": "Holdings exist only as of the moment they are read. {readings}"},
    "fct_token_holders": {"kind": "snapshot", "cadence": "snapshot", "why": "Top holders exist only as of the moment they are read. {readings}"},
    "fct_validator_epoch": {"kind": "backfill", "cadence": "daily", "job": "validators", "why": "One finished epoch per day, the one in force at the day's first block, asked of the archival node newest first: {validator_pace} epochs a night back to {validators_from}. {validators_note}", "done_kind": "full", "done_why": "One finished epoch per day, the one in force at the day's first block, from {validators_from}, where the daily blocks of dim_block_day begin. Older epochs are not asked for. {validators_note}"},
    "fct_validator_summary": {"kind": "backfill", "cadence": "daily", "job": "validators", "why": "Summarises fct_validator_epoch, so it fills at the same pace. {validators_note}", "done_kind": "full", "done_why": "Summarises fct_validator_epoch: one finished epoch per day from {validators_from}. {validators_note}"},
    "fct_chain_signatures_daily": {"kind": "window", "cadence": "daily", "why": "NearBlocks /v3 signer statistics serve the last 365 days, so history starts on {first} and grows one day a night."},
    "fct_mpc_state": {"kind": "backfill", "cadence": "blockday", "unit": "days", "job": "views", "why": "v1.signer read at the first block of a day: every day from {daily_from}, and one day a month before that. The nightly job replays past days newest first, {views_pace} days a night.", "done_kind": "full", "done_why": "v1.signer read at the first block of a day: every day from {daily_from}, and one day a month before that, back to {first_month}, the contract's first month. A day on which the contract was not in its Running state has no row. {views_note}"},
    "fct_mpc_participants": {"kind": "backfill", "cadence": "blockday", "unit": "days", "job": "views", "why": "v1.signer read at the first block of a day: every day from {daily_from}, and one day a month before that. The nightly job replays past days newest first, {views_pace} days a night.", "done_kind": "full", "done_why": "v1.signer read at the first block of a day: every day from {daily_from}, and one day a month before that, back to {first_month}, the contract's first month. A day on which the contract was not in its Running state has no rows. {views_note}"},
    "fct_mpc_operators": {"kind": "snapshot", "cadence": "snapshot", "why": "NearBlocks' operator list as of each nightly read. {readings}"},
    "fct_lst_snapshot": {"kind": "backfill", "cadence": "blockday", "unit": "days", "job": "views", "why": "Each liquid staking contract read at the first block of a day: every day from {daily_from}, and one day a month before that. The nightly job replays past days newest first, {views_pace} days a night.", "done_kind": "full", "done_why": "Each liquid staking contract read at the first block of a day: every day from {daily_from}, and one day a month before that, back to its first month. {series_oldest_name} starts on {first} and {series_newest_name} on {series_newest}. {views_note}"},
    "fct_protocol_tvl_daily": {"kind": "full", "cadence": "daily", "why": "DefiLlama's full TVL history for {series_total} protocols on NEAR, each from its own first day: {first} for the oldest, {series_newest} for the newest. {tvl_note}"},
    "fct_defi_tvl_daily": {"kind": "full", "cadence": "daily", "why": "DefiLlama's TVL for the NEAR chain, every day since {first}."},
    "fct_exchange_balance_daily": {"kind": "full", "cadence": "daily", "why": "DefiLlama's full history for {series_total} exchanges' wallets on NEAR, each from its own first day: {first} for the oldest, {series_newest} for the newest. {tvl_note}"},
    "fct_protocol_fees_snapshot": {"kind": "snapshot", "cadence": "snapshot", "why": "DefiLlama's fees overview as of each nightly read. {readings}"},
    "fct_stablecoin_assets": {"kind": "snapshot", "cadence": "snapshot", "why": "DefiLlama's stablecoin list as of each nightly read. {readings}"},
    "fct_yield_pools": {"kind": "snapshot", "cadence": "snapshot", "why": "DefiLlama's yield pools as of each nightly read. {readings}"},
    "fct_market_daily": {"kind": "full", "cadence": "daily", "why": "Every day since {first}. Prices and market cap start on {c[price_usd]}, the first priced day."},
    "fct_token_prices": {"kind": "snapshot", "cadence": "snapshot", "why": "Price lists show today's prices only. {readings}"},
    "fct_token_price_daily": {"kind": "full", "cadence": "daily", "why": "Each asset starts on the first day of its price series, from {series_oldest_name} on {first} to {series_newest_name} on {series_newest}. The fetch asks for prices from 2024-11-01, the first month the pool's balances are read from the chain, and reads the newest days again each night."},
    "fct_peer_daily": {"kind": "full", "cadence": "daily", "why": "Each chain starts on the first day its sources report, from {series_oldest_name} on {first} to {series_newest_name} on {series_newest}."},
    "fct_peer_app_fees_snapshot": {"kind": "snapshot", "cadence": "snapshot", "why": "DefiLlama's fee and revenue lists for each chain as of each nightly read. {readings}"},
    "fct_peer_chain_fees_snapshot": {"kind": "snapshot", "cadence": "snapshot", "why": "Each chain's own row in DefiLlama's fee lists as of each nightly read. {readings}"},
    "fct_swap_services_daily": {"kind": "full", "cadence": "daily", "why": "Each service starts on the first day its source reports, from {series_oldest_name} on {first} to {series_newest_name} on {series_newest}. NEAR Intents' days are fct_intents_daily's, and the others are DefiLlama's full history, read again each night."},
    "fct_peer_supply_readings": {"kind": "reference", "date": "reading_date", "why": "Each peer's total supply was read once by hand and is kept in registry/peer_supply_readings.csv. The newest reading is dated {last}."},
    "fct_etf_nrr_daily": {"kind": "full", "cadence": "trading", "why": "Every trading day from {first}. The first row is the fund's seed capital, the day before trading began."},
    "fct_etf_nrr_chain_daily": {"kind": "full", "cadence": "daily", "why": "Every day since {first}, the day the fund's seed NEAR arrived on chain."},
    "fct_dev_activity_weekly": {"kind": "window", "cadence": "weekly", "why": "The fetcher reads the last {commit_weeks} weeks of commits, so history starts on {first} and grows a week at a time. GitHub keeps older commits; reading them needs a longer window in ingest/sources/ecosystem.py."},
    "fct_repo_snapshot": {"kind": "snapshot", "cadence": "snapshot", "why": "Stars, forks and last push as of each nightly read. {readings}"},
    "fct_catalog_projects": {"kind": "snapshot", "cadence": "snapshot", "why": "NEAR Catalog as of each nightly read. {readings}"},
    "fct_governance_threads": {"kind": "snapshot", "cadence": "snapshot", "why": "Thread engagement as of each nightly read. {readings}"},
    "fct_governance_proposals": {"kind": "full", "cadence": "event", "date": "created_date", "why": "Every House of Stake proposal, read from vote.dao each night. The first was created on {first} and the newest on {last}."},
    "fct_governance_decisions": {"kind": "full", "cadence": "event", "date": "voting_start_date", "why": "Every real vote on vote.dao with what it decides, read by hand from each proposal's text (registry/governance_decisions.csv). Voting on the first opened on {first} and on the newest on {last}."},
    "fct_venear_snapshot": {"kind": "backfill", "cadence": "blockday", "unit": "days", "job": "views", "why": "venear.dao read at the first block of each day. The nightly job replays past days newest first, {views_pace} days a night.", "done_kind": "full", "done_why": "venear.dao read at the first block of each day since {first}, the first day the contract existed. {views_note}"},
    "fct_thesis_scorecard": {"kind": "reference", "date": "as_of_date", "why": "Rebuilt on every build: each claim in dim_claim is measured on the newest data its test can read, which falls between {first} and {last}. One row per claim, with no time axis."},
    "dim_claim": {"kind": "reference", "why": "The claims the scorecard tests, kept by hand in registry/claims.csv."},
    "fct_net_dilution_daily": {"kind": "full", "cadence": "daily", "why": "Built from fct_supply_daily, so it starts on {first}, the first day with 30 days of supply behind it. Issuance in dollars starts on {c[minted_30d_usd]}, once 30 days of prices exist, and the staking columns on {c[staked_share]}, with the validator history."},
    "fct_deflation_scenarios": {"kind": "reference", "date": "as_of_date", "why": "Rebuilt on every build from the 30 days ending on {last}. One row per issuance scenario and share of fees kept, with no time axis."},
    "fct_intents_unit_economics_monthly": {"kind": "full", "cadence": "monthly", "why": "One row per month since the first Intents volume in {first_month}, built from fct_intents_daily. Fees and revenue start in {cm[fees_usd]}. The newest month is short, which is_month_complete marks."},
    "fct_intents_channel_economics_monthly": {"kind": "full", "cadence": "monthly", "why": "Built from the unbroken daily run of fct_intents_1click_channel_daily, which starts on {oneclick_run_from}, so {first_month} is a part month. The newest month is short too, which is_month_complete marks."},
    "fct_intents_concentration_monthly": {"kind": "full", "cadence": "monthly", "why": "Four cuts, each starting where its input does. The two 1Click channel cuts start in {first_month}; the cuts of public volume by blockchain and by asset start later, because NearBlocks /v3 serves only the last 365 days."},
    "fct_valuation_multiples_daily": {"kind": "full", "cadence": "daily", "why": "Built from fct_peer_daily. Each chain starts once it has a market cap and 30 days of income, from {series_oldest_name} on {first} to {series_newest_name} on {series_newest}."},
    "fct_usage_quality_daily": {"kind": "window", "cadence": "daily", "why": "Limited by fct_contract_daily: NearBlocks' per-account statistics reach back 365 active days from their first read, so the table starts on {first}, where the Kai-Ching accounts' statistics do. The Sweat columns start on {c[sweat_relayer_txns]}."},
    "fct_usage_lead_correlations": {"kind": "reference", "date": "first_week", "why": "Rebuilt on every build from the weekly changes of its four inputs. The earliest block of seven days a correlation reads starts on {first}. One row per correlation, with no time axis."},
    "fct_etf_absorption_daily": {"kind": "full", "cadence": "trading", "why": "One row per trading day from {first}, the fund's first trading day, built from fct_etf_nrr_daily."},
    "dq_reconciliation": {"kind": "reference", "why": "Rebuilt on every build from the current data."},
    "dq_freshness": {"kind": "reference", "why": "Rebuilt on every build from the current data."},
    "dq_revisions": {"kind": "reference", "why": "Rebuilt on every build by comparing the first and last snapshot of each value."},
    "dq_ingest_runs": {"kind": "snapshot", "cadence": "snapshot", "why": "One row per dataset per nightly run. {readings}"},
    "dq_provenance": {"kind": "snapshot", "cadence": "snapshot", "why": "One row per dataset per snapshot. {readings}"},
}
# Tables that hold several series with their own start dates. The timeline draws how many are present on each day,
# so a bar that starts with one chain or wallet does not read as the whole table. `label` is the column to name them by.
SERIES: Dict[str, Dict[str, str]] = {
    "fct_peer_daily": {"key": "chain_id", "noun": "chain", "plural": "chains"},
    "fct_protocol_tvl_daily": {"key": "protocol_id", "label": "protocol_name", "noun": "protocol", "plural": "protocols"},
    "fct_exchange_balance_daily": {"key": "protocol_id", "label": "exchange_name", "noun": "exchange", "plural": "exchanges"},
    "fct_wallet_balance_daily": {"key": "account_id", "noun": "wallet", "plural": "wallets"},
    "fct_wallet_flows_daily": {"key": "account_id", "noun": "wallet", "plural": "wallets"},
    "fct_wallet_transfers": {"key": "account_id", "noun": "wallet", "plural": "wallets"},
    "fct_revenue_inflows_daily": {"key": "account_id", "noun": "wallet", "plural": "wallets"},
    "fct_contract_daily": {"key": "account_id", "noun": "contract", "plural": "contracts"},
    "fct_lst_snapshot": {"key": "token", "noun": "token", "plural": "tokens"},
    "fct_intents_concentration_monthly": {"key": "dimension", "noun": "cut", "plural": "cuts"},
    "fct_valuation_multiples_daily": {"key": "chain_id", "noun": "chain", "plural": "chains"},
    "fct_swap_services_daily": {"key": "service_id", "label": "service_name", "noun": "service", "plural": "services"},
    "fct_token_price_daily": {"key": "symbol", "noun": "asset", "plural": "assets"},
    "fct_dune_intents_chain_daily": {"key": "blockchain", "noun": "blockchain", "plural": "blockchains"},
    "fct_dune_intents_tvl_daily": {"key": "scope", "noun": "kind of balance", "plural": "kinds of balance"},
}
# Rows of these tables name accounts that are not in the registry, so the site shows no sample of them.
NO_SAMPLE = {"fct_token_holders", "fct_wallet_counterparties", "fct_wallet_transfers"}
SAMPLE_ROWS = 5
# What a table's history is counted in, by cadence. Event tables have no fixed period, so they show none.
PERIODS = {"daily": "days", "weekly": "weeks", "monthly": "months", "trading": "trading days", "blockday": "blocks", "snapshot": "readings"}
# The free GitHub Actions minutes a private repository gets each month (docs/audits/DATA_AUDIT_2026-11-05_SECOND_PASS.md).
# The queue's caveat is worked out from this and the run reports; set it to 0 once the repository is public.
ACTIONS_FREE_MINUTES = 0
CHAIN_NAMES = {"ethereum": "Ethereum", "solana": "Solana", "avalanche": "Avalanche", "near": "NEAR", "ton": "TON", "aptos": "Aptos", "sui": "Sui"}


def epoch_day(d: date) -> int:
    return (d - EPOCH).days


def runs(days: Iterable[int]) -> List[List[int]]:
    """Consecutive day numbers as [start, length] pairs."""
    out: List[List[int]] = []
    for d in sorted(set(days)):
        if out and d == out[-1][0] + out[-1][1]:
            out[-1][1] += 1
        else:
            out.append([d, 1])
    return out


def from_day(n: int) -> date:
    return EPOCH + timedelta(days=n)


def month_end(d: date) -> date:
    nxt = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    return nxt - timedelta(days=1)


def covered_days(cadence: str, dates: Sequence[date], last_day: date) -> Set[int]:
    """The days a table's dates cover, by its cadence."""
    if not dates:
        return set()
    days: Set[int] = set()
    if cadence == "event":  # no row means nothing happened, so the table is current through the latest data day
        return set(range(epoch_day(min(dates)), epoch_day(max(max(dates), last_day)) + 1))
    for d in dates:
        if cadence == "weekly":
            days.update(epoch_day(d) + i for i in range(7) if d + timedelta(days=i) <= last_day)
        elif cadence == "monthly":
            end = min(month_end(d), last_day)
            days.update(range(epoch_day(d), epoch_day(end) + 1))
        else:
            days.add(epoch_day(d))
    if cadence == "trading":  # a gap of weekend days between trading days, or after the last one, is not missing data
        ordered = sorted(dates)
        for a, b in zip(ordered, ordered[1:] + [last_day + timedelta(days=1)]):
            gap = [a + timedelta(days=i) for i in range(1, (b - a).days)]
            if gap and all(g.weekday() >= 5 for g in gap):
                days.update(epoch_day(g) for g in gap)
    return days


def readings_text(dates: Sequence[date]) -> str:
    """How many readings a point-in-time table holds and when they were taken, in words."""
    spans = runs(epoch_day(d) for d in dates)
    count = sum(length for _, length in spans)
    if count == 1:
        return f"One reading so far, on {iso(min(dates))}."
    if len(spans) == 1:
        return f"{count} readings so far, one a night since {iso(min(dates))}."
    parts = []
    for i, (start, length) in enumerate(spans):
        if length == 1:
            parts.append(iso(from_day(start)))
        elif i == len(spans) - 1:
            parts.append(f"every night from {iso(from_day(start))}")
        else:
            parts.append(f"{iso(from_day(start))} to {iso(from_day(start + length - 1))}")
    return f"{count} readings so far: {', then '.join(parts)}."


def iso(d: Any) -> Optional[str]:
    return d.isoformat() if isinstance(d, (date, datetime)) else (str(d) if d is not None else None)


def cell(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float):
        if math.isnan(value):
            return None
        size = abs(value)
        if size >= 1e15:
            return f"{value:.4e}"
        # six significant digits would turn 33,146,313 into 3.31463e+07
        return f"{value:.0f}" if size >= 1e6 else f"{value:.6g}"
    text = iso(value) if isinstance(value, (date, datetime)) else str(value)
    return text if len(text) <= 60 else text[:57] + "..."


class Site:
    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        self.pin = date.fromisoformat((ROOT / "data" / "PINNED").read_text().strip())
        self.last_day = self.con.execute("select mode(latest_data_day) from gold.dq_freshness").fetchone()[0]
        self.next_run = self.pin + timedelta(days=1)
        self.manifest = json.loads((ROOT / "warehouse" / "target" / "manifest.json").read_text())

    # ---------------------------------------------------------------- coverage
    def date_source(self, table: str, columns: List[str]) -> Tuple[Optional[str], str]:
        """The date expression for a table and the FROM clause it needs."""
        if table == "fct_validator_summary":
            return "approx_date_day", 'gold."fct_validator_summary"'
        if table == "fct_validator_epoch":
            return ("s.approx_date_day", 'gold."fct_validator_epoch" e left join (select epoch_height, approx_date_day from '
                    'gold."fct_validator_summary") s using (epoch_height)')
        override = HISTORY.get(table, {}).get("date")
        if override:
            return override, f'gold."{table}"'
        return next((c for c in DATE_COLUMNS if c in columns), None), f'gold."{table}"'

    def column_coverage(self, table: str, columns: List[str], date_expr: Optional[str], source: str) -> Dict[str, Dict[str, Any]]:
        parts = []
        for c in columns:
            q = f'"{c}"' if not date_expr or not date_expr.startswith("s.") else f'e."{c}"'
            parts.append(f"count({q})")
            if date_expr:
                parts.append(f"min(case when {q} is not null then {date_expr} end)")
                parts.append(f"max(case when {q} is not null then {date_expr} end)")
                parts.append(f"count(distinct case when {q} is not null then {date_expr} end)")
        row = self.con.execute(f"select count(*), {', '.join(parts)} from {source}").fetchone()
        total, values, out = row[0], list(row[1:]), {}
        step = 4 if date_expr else 1
        for i, c in enumerate(columns):
            chunk = values[i * step:(i + 1) * step]
            entry: Dict[str, Any] = {"nonnull": round(chunk[0] / total, 4) if total else 0, "nulls": total - chunk[0]}
            if date_expr:
                entry.update(first=iso(chunk[1]), last=iso(chunk[2]), days=chunk[3])
            out[c] = entry
        # A column that starts late or stops early is judged on the rows inside its own date range, so a table of
        # several series does not hide one that never has the value (TON's market cap in fct_peer_daily).
        ranged = [c for c in columns if out[c].get("first") and out[c]["nulls"]]
        if ranged:
            counts = self.con.execute("select " + ", ".join(
                f"count(*) filter (where {date_expr} between date '{out[c]['first']}' and date '{out[c]['last']}')" for c in ranged)
                + f" from {source}").fetchone()
            for c, n in zip(ranged, counts):
                out[c]["range_rows"] = n
        return out

    def dates(self, date_expr: str, source: str) -> List[date]:
        return [r[0] for r in self.con.execute(f"select distinct {date_expr} from {source} where {date_expr} is not null").fetchall()]

    def series(self, table: str, cadence: Optional[str], date_expr: str) -> Optional[Dict[str, Any]]:
        """The series inside a table (chains, wallets, protocols), when each starts, and how many are present each day."""
        spec = SERIES.get(table)
        if not spec:
            return None
        key, label = spec["key"], spec.get("label", spec["key"])
        rows = self.con.execute(
            f'select max("{label}"), min({date_expr}), max({date_expr}), count(distinct {date_expr}) '
            f'from gold."{table}" group by "{key}" order by 2, 1').fetchall()
        if len(rows) < 2:
            return None
        steps: List[List[int]] = []
        if cadence == "event":  # rows only on active days, so a series counts from its first day on
            starts = sorted(epoch_day(r[1]) for r in rows)
            marks = sorted(set(starts)) + [max(epoch_day(self.last_day), starts[-1]) + 1]
            steps = [[a, b - a, bisect_right(starts, a)] for a, b in zip(marks, marks[1:])]
        else:
            per_day = self.con.execute(f'select {date_expr}, count(distinct "{key}") from gold."{table}" group by 1 order by 1').fetchall()
            for d, n in per_day:
                day, length = epoch_day(d), 1
                if cadence == "monthly":  # a month's row stands for its days, as it does for a table of one series
                    length = max(1, (min(month_end(d), self.last_day) - d).days + 1)
                elif cadence == "weekly":
                    length = max(1, min(7, (self.last_day - d).days + 1))
                if steps and steps[-1][2] == n and steps[-1][0] + steps[-1][1] == day:
                    steps[-1][1] += length
                else:
                    steps.append([day, length, n])
        names = CHAIN_NAMES if key == "chain_id" else {}
        return {"noun": spec["noun"], "plural": spec["plural"], "total": len(rows), "steps": steps,
                "list": [{"name": names.get(str(r[0]), str(r[0])), "first": iso(r[1]), "last": iso(r[2]), "days": r[3]} for r in rows]}

    # ---------------------------------------------------------------- lineage and samples
    def lineage(self) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        nodes = {k: v for k, v in self.manifest["nodes"].items() if v["resource_type"] in ("model", "seed")}
        reads: Dict[str, List[str]] = {}
        read_by: Dict[str, List[str]] = defaultdict(list)
        for node in nodes.values():
            if node["resource_type"] != "model" or node["schema"] != "gold":
                continue
            parents = sorted({nodes[p]["name"] for p in node["depends_on"]["nodes"] if p in nodes})
            reads[node["name"]] = parents
            for p in parents:
                read_by[p].append(node["name"])
        return reads, {k: sorted(v) for k, v in read_by.items()}

    def sample(self, table: str, columns: List[str], date_col: Optional[str]) -> Optional[Dict[str, Any]]:
        if table in NO_SAMPLE:
            return None
        key = date_col if date_col and date_col in columns else ("epoch_height" if "epoch_height" in columns else None)
        # Every column breaks a tie, so the same warehouse always gives the same sample
        ties = ", ".join(f'"{c}"' for c in columns)
        order = f'order by "{key}" desc nulls last, {ties}' if key else f"order by {ties}"
        rows = self.con.execute(f'select * from gold."{table}" {order} limit {SAMPLE_ROWS}').fetchall()
        return {"rows": [[cell(v) for v in r] for r in rows]} if rows else None

    # ---------------------------------------------------------------- backfill jobs
    def jobs(self) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Set[int]]]]:
        """Progress of every long history job, and the days each one has and still needs, for the timeline."""
        cover: Dict[str, Dict[str, Set[int]]] = {}
        jobs = [self.explorer_job(cover), self.receiver_job(cover), self.validator_job(cover), self.views_job(cover),
                self.ft_metadata_job(), self.transfers_job(), self.block_day_job(), self.dune_job()]
        return jobs, cover

    def _manifest_rows(self, source: str, dataset: str) -> List[Dict[str, Any]]:
        rows = []
        for path in sorted((ROOT / "data" / "bronze" / "_manifest").glob("dt=*.jsonl")):
            for line in path.read_text().splitlines():
                r = json.loads(line)
                if r.get("source") == source and r.get("dataset") == dataset:
                    rows.append(r)
        return rows

    def _run_seconds(self, dataset: str) -> Optional[float]:
        runs_dir = ROOT / "data" / "bronze" / "_runs"
        latest = sorted(runs_dir.glob("dt=*.json"))
        if not latest:
            return None
        report = json.loads(latest[-1].read_text())
        return (report.get(dataset) or {}).get("seconds")

    def explorer_job(self, cover: Dict[str, Dict[str, Set[int]]]) -> Dict[str, Any]:
        state = json.loads((STATE / "intents_explorer__daily_tally.json").read_text())["days"]
        start = intents.EXPLORER_FROM
        wanted = [start + timedelta(days=i) for i in range((self.last_day - start).days + 1)]
        walked = [d for d in wanted if d.isoformat() in state]
        pending = [d for d in wanted if d.isoformat() not in state]
        first_swap = min((d for d in walked if state[d.isoformat()] > 0), default=None)
        # Pages per day, by month, from the days already walked; a month not sampled yet takes its nearest neighbour.
        pages: Dict[str, List[int]] = defaultdict(list)
        for r in self._manifest_rows("intents_explorer", "daily_tally"):
            p = r.get("params") or {}
            if p.get("day") and p.get("pages"):
                pages[p["day"][:7]].append(p["pages"])
        monthly = {m: sum(v) / len(v) for m, v in pages.items()}
        months = sorted(monthly)

        def pages_for(d: date) -> float:
            if first_swap and d < first_swap:
                return 1.0
            m = d.strftime("%Y-%m")
            if m in monthly:
                return monthly[m]
            nearest = min(months, key=lambda x: abs((date.fromisoformat(x + "-01") - date.fromisoformat(m + "-01")).days)) if months else None
            return monthly[nearest] if nearest else 1.0

        recent = [pages_for(self.last_day - timedelta(days=i)) for i in range(intents.EXPLORER_RECENT_DAYS)]
        budget = intents.EXPLORER_PAGES_PER_RUN - sum(recent)
        queue = sorted(pending, reverse=True)
        est_pages = sum(pages_for(d) for d in queue)
        nights = 0
        while queue and nights < 400:
            nights += 1
            left = budget
            while queue and pages_for(queue[0]) <= left:
                left -= pages_for(queue.pop(0))
        before_first = sum(1 for d in pending if first_swap and d < first_swap)
        # A walked day before 1Click's first swap is known to be empty, so the tables' history starts at that swap.
        have = {epoch_day(d) for d in walked if not first_swap or d >= first_swap}
        cover["explorer"] = {"have": have, "pending": {epoch_day(d) for d in pending}}
        empty_before = sum(1 for d in walked if first_swap and d < first_swap)
        empty_since = sum(1 for d in walked if first_swap and d > first_swap and not state[d.isoformat()])
        finished = (f"Every day from {iso(start)} to {iso(self.last_day)} has been walked. 1Click's first swap is on {iso(first_swap)}: "
                    f"the {empty_before} days before it came back empty"
                    + (f", and {empty_since} days since had no swap" if empty_since else "")
                    + f". The last {intents.EXPLORER_RECENT_DAYS} days are tallied again each night, because a swap's status can still change.")
        seconds = self._run_seconds("intents_explorer/daily_tally")
        return {
            "id": "explorer", "label": "1Click day tallies", "source": "Intents Explorer API",
            "status": "running" if pending else "done", "unit": "days", "done": len(walked), "total": len(wanted),
            "remaining": len(pending), "nights": nights if pending else 0,
            "eta": iso(self.pin + timedelta(days=nights)) if pending else None,
            "pace": f"{intents.EXPLORER_PAGES_PER_RUN} pages a night", "minutes": round(seconds / 60) if seconds else None,
            "from": iso(start), "empty_since": empty_since,
            "detail": finished if not pending else (f"Walked: one day a week back to {iso(start)}, and every day since {iso(min((d for d in wanted if d > max(pending)), default=self.last_day)) if pending else iso(start)}. "
                       f"About {round(est_pages):,} pages remain at roughly {round(budget)} a night once the last {intents.EXPLORER_RECENT_DAYS} days are re-read. "
                       + (f"{before_first} of the {len(pending)} days fall before 1Click's first swap on {iso(first_swap)}, so they should come back empty and cost a page each." if before_first else "")),
        }

    def receiver_job(self, cover: Dict[str, Dict[str, Set[int]]]) -> Dict[str, Any]:
        done = json.loads((STATE / "neardata__receiver_sample.json").read_text())
        window = [self.pin - timedelta(days=b) for b in range(1, RECEIVER_WINDOW_DAYS + 1)]
        have = [d for d in window if d.isoformat() in done]
        pending = sorted((d for d in window if d.isoformat() not in done), reverse=True)
        nights, queue, today = 0, list(pending), self.next_run
        while queue and nights < 400:
            nights += 1
            oldest = today - timedelta(days=RECEIVER_WINDOW_DAYS)
            queue = [d for d in queue if d >= oldest][neardata.BACKFILL_DAYS_PER_RUN:]
            today += timedelta(days=1)
        cover["receiver"] = {"have": {epoch_day(date.fromisoformat(d)) for d in done}, "pending": {epoch_day(d) for d in pending}}
        seconds = self._run_seconds("neardata/receiver_sample_backfill")
        return {
            "id": "receiver", "label": "Receiver sample", "source": "Neardata blocks",
            "status": "running" if pending else "done", "unit": "days", "done": len(have), "total": len(window),
            "remaining": len(pending), "nights": nights if pending else 0,
            "eta": iso(self.pin + timedelta(days=nights)) if pending else None,
            "pace": f"{neardata.BACKFILL_DAYS_PER_RUN} days a night", "minutes": round(seconds / 60) if seconds else None,
            "from": iso(window[-1]),
            "detail": (f"A rolling window of the last {RECEIVER_WINDOW_DAYS} days, filled newest first at {neardata.BACKFILL_BLOCKS_PER_DAY} blocks a day "
                       f"(new days get {neardata.BLOCKS_PER_DAY}). Days that slide out of the window are not fetched, so the table will hold about a year."
                       if pending else
                       f"The {RECEIVER_WINDOW_DAYS} days before the first run were sampled at {neardata.BACKFILL_BLOCKS_PER_DAY} blocks a day and are all in. "
                       f"Each new day is sampled at {neardata.BLOCKS_PER_DAY}. Older days are not fetched."),
        }

    def validator_job(self, cover: Dict[str, Dict[str, Set[int]]]) -> Dict[str, Any]:
        state = json.loads((STATE / "rpc__validators_epoch.json").read_text())
        asks = dict(state.get("refused") or {})
        for epoch_id in state.get("unavailable", []):  # the state an earlier fetcher wrote, which gave up after one refusal
            asks.setdefault(epoch_id, 1)
        limit = rpc.VALIDATOR_ASKS_PER_EPOCH
        done = set(state["done"]) | rpc._epochs_on_file()
        given_up = {e for e, n in asks.items() if n >= limit} - done
        # The job asks for one finished epoch per day: the one in force at the day's first block.
        days = self.con.execute("select date_day, epoch_id from gold.dim_block_day where date_day >= ? order by 1", [rpc.DAILY_FROM]).fetchall()
        have = {d for d, e in days if e in done}
        refused = {d for d, e in days if e in given_up}
        pending = {d for d, e in days if e not in done and e not in given_up}
        again = sum(1 for d, e in days if e in asks and e not in done and e not in given_up)
        nights = math.ceil(len(pending) / rpc.VALIDATOR_EPOCHS_PER_RUN) if pending else 0
        cover["validators"] = {"have": {epoch_day(d) for d in have}, "pending": {epoch_day(d) for d in pending},
                               "refused": {epoch_day(d) for d in refused}}
        asked_again = (f"The archival host's nodes do not all hold the same epochs, so an epoch one of them refuses is asked again "
                       f"on later runs, up to {limit} times.")
        if not pending and not refused:
            note = f"Every day has its epoch. {asked_again}"
        else:
            note = f"{len(have):,} of {len(days):,} days have their epoch. {asked_again}"
            if again:
                note += f" {again} refused so far are waiting to be asked again."
            if refused:
                note += f" {len(refused)} were refused {limit} times and stay empty."
        return {
            "id": "validators", "label": "Validator epochs", "source": "Archival RPC",
            "status": "running" if pending else "done", "unit": "days", "done": len(have), "total": len(days),
            "remaining": len(pending), "refused": len(refused), "tried": len(have) + len(refused), "nights": nights,
            "eta": iso(self.pin + timedelta(days=nights)) if pending else None, "oldest": iso(min(have)) if have else None,
            "pace": f"{rpc.VALIDATOR_EPOCHS_PER_RUN} epochs a night", "minutes": None, "from": iso(rpc.DAILY_FROM),
            "note": note,
            "detail": f"One finished epoch per day, the one in force at the day's first block, back to {iso(rpc.DAILY_FROM)}. {note}",
        }

    def views_job(self, cover: Dict[str, Dict[str, Set[int]]]) -> Dict[str, Any]:
        """Contract views replayed at the first block of each day dim_block_day holds. Bronze is the record of days done."""
        wanted = {r[0] for r in self.con.execute("select date_day from gold.dim_block_day").fetchall()}
        files = (ROOT / "data" / "bronze" / "rpc" / "contract_views_history").glob("dt=*/*.json.gz")
        done = {date.fromisoformat(path.name.split(".")[0]) for path in files} & wanted
        pending = wanted - done
        nights = math.ceil(len(pending) / rpc.VIEW_HISTORY_DAYS_PER_RUN) if pending else 0
        cover["views"] = {"have": {epoch_day(d) for d in done}, "pending": {epoch_day(d) for d in pending}}
        contracts = sorted({contract for contract, _, _ in rpc.VIEW_HISTORY_CALLS})
        return {
            "id": "views", "label": "Contract state replay", "source": "Archival RPC",
            "status": "running" if pending else "done", "unit": "days", "done": len(done), "total": len(wanted),
            "remaining": len(pending), "nights": nights, "eta": iso(self.pin + timedelta(days=nights)) if pending else None,
            "pace": f"{rpc.VIEW_HISTORY_DAYS_PER_RUN} days a night", "minutes": None, "from": iso(min(wanted)) if wanted else None,
            "note": ("Every day dim_block_day holds has been replayed." if not pending
                     else f"{len(done):,} of the {len(wanted):,} days dim_block_day holds have been replayed."),
            "detail": (f"Views of {len(contracts)} contracts ({', '.join(contracts)}) replayed at the first block of each day dim_block_day holds: "
                       f"every day from {iso(rpc.DAILY_FROM)}, and the first of each month before. "
                       "A contract found absent on two newer days is not asked about on older ones."),
        }

    def ft_metadata_job(self) -> Dict[str, Any]:
        state = json.loads((STATE / "rpc__ft_metadata.json").read_text())
        answered = set(state["answers"])
        seen = rpc._tokens_seen()
        remaining = len([t for t in seen if t not in answered])
        return {
            "id": "ft_metadata", "label": "Token metadata", "source": "RPC ft_metadata",
            "status": "running" if remaining > 50 else "done", "unit": "tokens", "done": len(answered & set(seen)), "total": len(seen),
            "remaining": remaining, "nights": math.ceil(remaining / rpc.FT_METADATA_CALLS_PER_RUN) if remaining else 0, "eta": None,
            "pace": f"{rpc.FT_METADATA_CALLS_PER_RUN:,} tokens a night", "minutes": None,
            "detail": "Decimals and symbols for every token seen in holdings and top holders, read once each. New tokens are read the night they appear.",
            "tables": ["fct_wallet_holdings"],
        }

    def transfers_job(self) -> Dict[str, Any]:
        state = json.loads((STATE / "fastnear__transfers.json").read_text())
        at_tail = sum(1 for v in state.values() if v.get("at_tail"))
        return {
            "id": "transfers", "label": "Wallet transfer crawls", "source": "FastNear Transfers API",
            "status": "done" if at_tail == len(state) else "running", "unit": "wallets", "done": at_tail, "total": len(state),
            "remaining": len(state) - at_tail, "nights": 0, "eta": None, "pace": f"up to {fastnear.NIGHTLY_PAGE_LIMIT} pages per wallet a night", "minutes": None,
            "detail": "Each crawled wallet read back to its first transfer. New transfers arrive nightly.",
            "tables": ["fct_wallet_transfers", "fct_wallet_flows_daily", "fct_wallet_balance_daily", "fct_revenue_inflows_daily", "fct_wallet_counterparties"],
        }

    def block_days_wanted(self) -> Set[date]:
        """The days dim_block_day is meant to hold: the first of each month, then every day."""
        wanted, d = set(), rpc.MONTHLY_FROM
        while d < rpc.DAILY_FROM:
            wanted.add(d)
            d = month_end(d) + timedelta(days=1)
        wanted.update(rpc.DAILY_FROM + timedelta(days=i) for i in range((self.pin - rpc.DAILY_FROM).days + 1))
        return wanted

    def block_day_job(self) -> Dict[str, Any]:
        present = {r[0] for r in self.con.execute("select date_day from gold.dim_block_day").fetchall()}
        wanted = self.block_days_wanted()
        missing = len(wanted - present)
        return {
            "id": "block_day", "label": "Daily blocks", "source": "Archival RPC",
            "status": "done" if not missing else "running", "unit": "days", "done": len(wanted & present), "total": len(wanted),
            "remaining": missing, "nights": math.ceil(missing / rpc.BLOCK_DAYS_PER_RUN) if missing else 0, "eta": None,
            "pace": f"{rpc.BLOCK_DAYS_PER_RUN} days a run", "minutes": None,
            "detail": f"The first block of each month from {iso(rpc.MONTHLY_FROM)}, and of each day from {iso(rpc.DAILY_FROM)}. Other jobs read their heights.",
            "tables": ["dim_block_day"],
        }

    def dune_job(self) -> Dict[str, Any]:
        last = self.con.execute("select max(snapshot_date) from gold.fct_intents_dashboard_readings").fetchone()[0]
        behind = (self.pin - last).days
        return {
            "id": "dune", "label": "Dune dashboard readings", "source": "NEAR's dashboard on Dune, read in a browser on request",
            "status": "manual", "unit": "readings", "done": self.con.execute("select count(distinct snapshot_date) from gold.fct_intents_dashboard_readings").fetchone()[0],
            "total": None, "remaining": None, "nights": None, "eta": None, "pace": "on request", "minutes": None, "last": iso(last),
            "detail": (f"The last reading was taken on {iso(last)}, {behind} {'day' if behind == 1 else 'days'} before the pin. "
                       "A reading is taken in a browser on request, never on a schedule, and recorded with tools/record_dune_reading.py."),
        }

    # ---------------------------------------------------------------- assemble
    def shared_facts(self, jobs: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Numbers the history sentences quote, read from the job state and the fetchers' settings."""
        transfers, block, dune = jobs["transfers"], jobs["block_day"], jobs["dune"]
        if transfers["remaining"]:
            crawl = (f"{transfers['done']} of the {transfers['total']} FastNear crawls have reached their wallet's first transfer; "
                     "the others are still walking back.")
        else:
            crawl = f"All {transfers['total']} FastNear crawls have reached their wallet's first transfer."
        return {
            "blocks_new": neardata.BLOCKS_PER_DAY, "blocks_old": neardata.BACKFILL_BLOCKS_PER_DAY,
            "receiver_pace": neardata.BACKFILL_DAYS_PER_RUN, "receiver_window": RECEIVER_WINDOW_DAYS,
            "explorer_pages": intents.EXPLORER_PAGES_PER_RUN, "explorer_full": intents.EXPLORER_FULL_DAYS,
            "explorer_from": iso(intents.EXPLORER_FROM),
            "validator_pace": rpc.VALIDATOR_EPOCHS_PER_RUN, "validators_from": iso(rpc.DAILY_FROM), "validators_note": jobs["validators"]["note"],
            "views_pace": rpc.VIEW_HISTORY_DAYS_PER_RUN, "views_note": jobs["views"]["note"],
            "explorer_recent": intents.EXPLORER_RECENT_DAYS,
            "explorer_empty": (f"{jobs['explorer']['empty_since']} days since the first swap had none." if jobs["explorer"]["empty_since"] else ""),
            "oneclick_run_from": iso(self.con.execute("select min(date_day) filter (where is_in_daily_run) from gold.fct_intents_1click_daily").fetchone()[0]),
            "monthly_from": rpc.MONTHLY_FROM.strftime("%B %Y"), "daily_from": rpc.DAILY_FROM.strftime("%B %Y"),
            "block_note": "Every wanted day is in." if not block["remaining"] else f"{block['remaining']} wanted days are still to fetch.",
            "commit_weeks": ecosystem.COMMITS_WEEKS, "crawl_note": crawl,
            "dune_cover": "the one reading so far covers" if dune["done"] == 1 else f"the {dune['done']} readings so far cover",
        }

    def actions_note(self, jobs: List[Dict[str, Any]]) -> str:
        """Whether the free Actions minutes outlast the backfills, worked out from this month's run reports."""
        running = [j for j in jobs if j["status"] == "running" and j.get("nights")]
        month = self.pin.strftime("%Y-%m")
        minutes = {}
        for path in sorted((ROOT / "data" / "bronze" / "_runs").glob(f"dt={month}-*.json")):
            minutes[path.stem[3:]] = sum((v or {}).get("seconds") or 0 for v in json.loads(path.read_text()).values()) / 60
        if not (ACTIONS_FREE_MINUTES and running and minutes and minutes[max(minutes)] > 0):
            return ""
        used, nightly = sum(minutes.values()), minutes[max(minutes)]
        nights = max(0, int((ACTIONS_FREE_MINUTES - used) // nightly))
        runs_out = self.pin + timedelta(days=nights)
        reset = month_end(self.pin) + timedelta(days=1)
        if runs_out >= reset:
            return ""
        need = sorted(j["nights"] for j in running)
        needs = f"{need[0]}" if need[0] == need[-1] else f"{need[0]} to {need[-1]}"
        verdict = (f"The backfills need {needs} more nights, so they are likely to stop short until the allowance resets on {iso(reset)}."
                   if nights < need[-1] else f"That covers the {needs} nights the backfills need.")
        return (f"If the repository is still private, its {ACTIONS_FREE_MINUTES:,} free GitHub Actions minutes a month are the tighter limit. "
                f"The run reports count about {round(used, -1):,.0f} minutes of fetching in {self.pin.strftime('%B')} so far, before setup, "
                f"the build and the tests, so at {round(nightly)} a night the allowance lasts at most {nights} more nights, to about {iso(runs_out)}. "
                f"{verdict} Making the repository public or setting a spending limit lifts the cap.")

    def tvl_note(self, table: str) -> str:
        """Where a DefiLlama table's protocols come from, stated only as far as the data bears it out."""
        top = defillama.TOP_NEAR_PROTOCOLS
        count = {t: self.con.execute(f'select count(distinct protocol_id) from gold."{t}"').fetchone()[0]
                 for t in ("fct_protocol_tvl_daily", "fct_exchange_balance_daily")}
        if sum(count.values()) != top:
            return f"The fetcher reads the {top} largest DefiLlama entries on NEAR by TVL each night."
        if table == "fct_protocol_tvl_daily":
            return (f"They are the protocols among the {top} largest DefiLlama entries on NEAR by TVL; the other "
                    f"{count['fct_exchange_balance_daily']} are exchanges, kept in fct_exchange_balance_daily.")
        return (f"They are the exchanges among the {top} largest DefiLlama entries on NEAR by TVL; the other "
                f"{count['fct_protocol_tvl_daily']} are protocols, kept in fct_protocol_tvl_daily.")

    def build(self) -> Dict[str, Any]:
        catalog = build_catalog(self.con)
        missing = {t["table"] for t in catalog} - set(HISTORY)
        if missing:
            raise SystemExit(f"Gold tables missing from HISTORY in tools/docsite.py: {sorted(missing)}")
        reads, read_by = self.lineage()
        jobs, cover = self.jobs()
        job_tables = defaultdict(list)
        for t in catalog:
            job = HISTORY[t["table"]].get("job")
            if job:
                job_tables[job].append(t["table"])
        for j in jobs:
            j.setdefault("tables", job_tables.get(j["id"], []))
        jobs_by_id = {j["id"]: j for j in jobs}
        shared = self.shared_facts(jobs_by_id)
        chain_start = self.con.execute("select min(date_day) from gold.fct_chain_daily").fetchone()[0]
        tables = []
        for t in catalog:
            name, h = t["table"], HISTORY[t["table"]]
            names = [c["name"] for c in t["columns"]]
            date_expr, source = self.date_source(name, names)
            date_col = date_expr if date_expr in names else None
            coverage = self.column_coverage(name, [n for n in names if n != date_col], date_expr, source)
            cadence = h.get("cadence")
            have: Set[int] = set()
            pending: Set[int] = set()
            refused: Set[int] = set()
            gaps: Set[int] = set()
            first = last = None
            dates: List[date] = []
            if date_expr:
                dates = self.dates(date_expr, source)
                if dates:
                    first, last = min(dates), max(dates)
                if cadence:
                    have = covered_days(cadence, dates, max(self.last_day, last or self.last_day))
            sorted_dates = sorted(dates)
            col_first, col_last = first, last
            job_cover = cover.get(h.get("job", ""))
            if job_cover:
                # The 1Click and validator jobs know which days they have asked for, so their state is the coverage:
                # a walked day with no swaps is covered though it has no row, and a refused epoch is settled though empty.
                if h["job"] in ("explorer", "validators"):
                    have = set(job_cover["have"])
                pending = job_cover["pending"] - have
                refused = job_cover.get("refused", set()) - have
                if h["job"] == "validators" and have:
                    first, last = from_day(min(have)), from_day(max(have))
            elif have and cadence not in ("event", "blockday") and not (h["kind"] == "hand" and cadence == "snapshot"):
                gaps = set(range(min(have), max(have) + 1)) - have
            if cadence == "blockday" and first:
                # Point reads at the first block of a day: a wanted day from the table's first on with no row is a gap.
                gaps = {epoch_day(d) for d in self.block_days_wanted() if d >= first} - have - pending
            # A table fed by a backfill is one while days are queued; once none are, it is whatever the finished job leaves.
            job = jobs_by_id.get(h.get("job", ""))
            finished = bool(job) and not job["remaining"]
            kind = h.get("done_kind", h["kind"]) if finished else h["kind"]
            why = h.get("done_why", h["why"]) if finished else h["why"]
            series = self.series(name, cadence, date_expr) if date_expr and cadence else None
            ending = sorted({m.group(1) for c in t["columns"] for m in [re.search(r"Ends on (\d{4}-\d{2}-\d{2})", c["description"])] if m})
            late = sorted(coverage[c]["first"] for c in names if first and coverage.get(c, {}).get("first")
                          and date.fromisoformat(coverage[c]["first"]) > first + timedelta(days=200)
                          and "365 days" in (next(x["description"] for x in t["columns"] if x["name"] == c) + t["description"]))
            facts = dict(shared)
            facts.update({
                "first": iso(first), "last": iso(last), "late_cols": len(late),
                "first_month": first.strftime("%B %Y") if first else "", "last_month": last.strftime("%B %Y") if last else "",
                "late_from": "" if not late else (f"on {late[0]}" if late[0] == late[-1] else f"between {late[0]} and {late[-1]}"),
                "ending_cols": sum(1 for c in t["columns"] if "Ends on" in c["description"]), "ends_on": ending[0] if ending else "",
                "readings": readings_text(dates) if cadence == "snapshot" and dates else "",
                "c": {c: v.get("first") for c, v in coverage.items()},
                "cm": {c: date.fromisoformat(v["first"]).strftime("%B %Y") if v.get("first") else "" for c, v in coverage.items()},
                "spine_note": ", the first day with chain data," if first == chain_start else "",
                "tvl_note": self.tvl_note(name) if name in ("fct_protocol_tvl_daily", "fct_exchange_balance_daily") else "",
                "series_total": series["total"] if series else "",
                "series_newest": series["list"][-1]["first"] if series else "",
                "series_oldest_name": series["list"][0]["name"] if series else "",
                "series_newest_name": series["list"][-1]["name"] if series else "",
            })
            columns = []
            for c in t["columns"]:
                entry = {"name": c["name"], "type": c["type"], "unit": c["unit"], "description": c["description"], **coverage.get(c["name"], {})}
                if c["name"] == date_col:
                    empty = self.con.execute(f'select count(*) - count("{date_col}") from {source}').fetchone()[0]
                    entry.update(first=iso(col_first), last=iso(col_last), days=len(dates), nulls=empty,
                                 nonnull=round(1 - empty / t["rows"], 4) if t["rows"] else 0)
                if date_expr and entry.get("first") and c["name"] != date_col:
                    lo, hi = date.fromisoformat(entry["first"]), date.fromisoformat(entry["last"])
                    entry["span_dates"] = bisect_right(sorted_dates, hi) - bisect_left(sorted_dates, lo)
                m = re.search(r"Ends on (\d{4}-\d{2}-\d{2})", c["description"])
                if m:
                    entry["ends"] = m.group(1)
                columns.append(entry)
            tables.append({
                "name": name, "area": t["area"], "description": t["description"], "grain": t["grain"], "sources": t["sources"],
                "path": t["path"], "rows": t["rows"], "first": iso(first), "last": iso(last),
                "through": iso(from_day(max(have))) if have else None,
                "date_col": date_col or ("epoch start day" if date_expr and date_expr.startswith("s.") else date_expr),
                "kind": kind, "why": " ".join(why.format(**facts).split()), "job": h.get("job"), "cadence": cadence,
                "have": runs(have), "pending": runs(pending), "refused": runs(refused), "gaps": runs(gaps),
                "have_days": len(have), "pending_days": len(pending), "refused_days": len(refused), "gap_days": len(gaps),
                "readings": len(dates) if cadence == "snapshot" else None, "series": series,
                "periods": {"n": len(have) if cadence == "daily" else len(dates), "unit": h.get("unit") or PERIODS[cadence]} if cadence in PERIODS else None,
                "sparse_before": iso(rpc.DAILY_FROM) if cadence == "blockday" and first and first < rpc.DAILY_FROM else None,
                "columns": columns, "reads": reads.get(name, []), "read_by": read_by.get(name, []),
                "sample": self.sample(name, names, date_col),
            })
        earliest = min(t["first"] for t in tables if t["first"] and t["kind"] != "reference")
        report = sorted((ROOT / "data" / "bronze" / "_runs").glob("dt=*.json"))
        nightly_minutes = round(sum((v or {}).get("seconds") or 0 for v in json.loads(report[-1].read_text()).values()) / 60) if report else None
        endings = sorted({c["ends"] for t in tables for c in t["columns"] if c.get("ends")})
        return {
            "meta": {"pin": iso(self.pin), "last_day": iso(self.last_day), "tables": len(tables), "columns": sum(len(t["columns"]) for t in tables),
                     "earliest": earliest, "chain_start": iso(chain_start),
                     "nightly_minutes": nightly_minutes,
                     "v1_off": endings[-1] if endings else None, "repo": "near-hub", "queue_note": self.actions_note(jobs)},
            "kinds": KINDS, "areas": [a for a, _ in AREAS], "tables": tables, "jobs": jobs,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fragment", type=Path, help="also write the page without its document wrapper, for hosts that add their own")
    parser.add_argument("--out", type=Path, default=OUT, help="where to write the page (default: site/docs/index.html)")
    parser.add_argument("--hub", help="the dashboard's folder as seen from the page, when it is not the repo's site/ folder")
    parser.add_argument("--hub-home", help="the full address of the dashboard, for a guide published by itself")
    args = parser.parse_args()
    out = args.out if args.out.is_absolute() else Path.cwd() / args.out
    os.chdir(ROOT)
    con = duckdb.connect("data/warehouse.duckdb", read_only=True)
    data = Site(con).build()
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    # Links to the dashboard are written relative to where the page lands, so it works from a folder and from a host
    hub = args.hub or os.path.relpath(HUB, out.parent).replace(os.sep, "/")
    # The folder, not its index.html, so the address bar shows nearhub.tech/ (a file:// copy adds index.html on click)
    home = args.hub_home or f"{hub}/"
    fragment = TEMPLATE.read_text().replace("__HUB_HOME__", home).replace("__HUB__", hub).replace("__DOCSITE_DATA__", payload)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                   '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                   f'{SHARE_TAGS}</head>\n<body>\n'
                   f"{fragment}\n</body>\n</html>\n")
    if args.fragment:
        # A host that wraps the page has no folder beside it, so the links to the dashboard's icons are left out
        args.fragment.write_text(re.sub(r'<link rel="icon"[^>]*>\n', "", fragment))
    running = [j for j in data["jobs"] if j["status"] == "running"]
    shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"Wrote {shown} ({len(data['tables'])} tables, {len(running)} backfills running, {out.stat().st_size / 1024:,.0f} KB)")


if __name__ == "__main__":
    main()
