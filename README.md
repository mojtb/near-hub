# NEAR Hub

An investment case for NEAR, tested claim by claim against public data that anyone can rebuild.

<!-- verdict:start -->
**Where the case stands at the snapshot of 2026-11-12:** of 19 claims the data can test, **10** support the long case and **9** count against it; **4** more cannot be tested from public data. Over the 30 days to 2026-11-09, fees reaching NEAR's revenue wallets and gas burned offset **16.1%** of the new NEAR the chain created.
<!-- verdict:end -->

Three things live here, and each is built from the one before it:

- **The warehouse.** Public on-chain, protocol, wallet and market data, collected every night, typed, joined into one
  documented set of tables and checked against itself. Every raw response is kept, so every number traces back to what
  a source actually said on the day it said it.
- **[THESIS.md](THESIS.md).** The long case for NEAR, set out as five links that depend on each other, with the
  evidence for and against each one and what would change the author's mind.
- **The dashboard, in `site/`.** The case on one page, then a subject at a time: each question with its chart, its
  reading and the query that produced it.

Neither the thesis nor the dashboard holds a typed number. Both are generated from the warehouse's claim scorecard, so
when the data moves they move with it, including the words. A claim that stops holding says so by itself.

## The problem this solves

Evidence about NEAR is scattered across a dozen services, and they disagree. Active accounts differ by 1.8x between two
versions of one API today, and differed by 9x to 18x before April 2026. Some "independent" sources read the same
NEAR-uploaded dataset. Price series are stamped a day apart. Free tiers and endpoints change or disappear. A thesis
built on that is hard to check and easy to fool yourself with.

This warehouse keeps every raw response, types it, joins it into shared tables, and publishes where sources disagree
instead of picking the convenient number.

## Try it

You need Python 3.11 and `make`. No keys and no API calls are needed for these steps; `make setup` downloads the
Python packages. `make all` runs steps 1, 2, 3, 6 and 7 in order.

1. Run `make setup`. See `Setup complete: N packages installed`.
2. Run `make warehouse`. See `Warehouse built as of ...`, in under a minute. This rebuilds `data/warehouse.duckdb` and `data/gold/` from the raw responses committed in `data/bronze/`.
3. Run `make verify`. See `10/10 checks passed`. This re-hashes every raw file, runs the data and unit tests, and confirms each gold table reproduces its committed fingerprint.
4. Run `make query SQL="select check_id, value_a, value_b, status from gold.dq_reconciliation order by status, check_id"`. See each comparison between sources.
5. Open [docs/RECONCILIATION.md](docs/RECONCILIATION.md). See where sources agree, where they don't, and why.
6. Run `make site`. See `Site built as of ...`, in a few seconds. This rewrites `site/shared/data.js` and `site/shared/catalog.js` from the warehouse you built in step 2, so every number and chart on the dashboard comes from those tables. It also rewrites `site/docs/index.html`, the guide to every table and field, which the dashboard links to from its Sources page and from the table names above each chart's query (`make docs` rebuilds the guide alone). Then open `site/index.html` in a browser; it needs a network connection for its fonts and chart library.
7. Run `make thesis`. See `wrote THESIS.md: ...`. This rewrites [THESIS.md](THESIS.md) from the same scorecard, and the file comes out unchanged unless the warehouse did.

If you prefer a container, run `docker build -t near-hub . && docker run --rm near-hub`. See the same
`10/10 checks passed`.

### Expected results

These lines are generated from the warehouse, and `make verify` fails if they stop matching it.

<!-- expected:start -->
- Data through: **2026-11-11**, the last full UTC day before the pinned snapshot of 2026-11-12; `dq_freshness` lists any source that ends earlier
- Gold tables and columns: **87** and **842**
- Reconciliation: **94** comparisons agree, **13** differ, each with a written explanation
- Issuance over the last 30 days, from supply change plus burn: **2.49%** a year, against **2.50%** in the protocol config
- Circulating supply, built from NEAR's lockup contracts: **1,309.38M** NEAR, **99.84%** of total supply; on 2025-08-26, the last day NearBlocks computed its own, **1,249.72M** against **1,249.65M**
- Captured Intents revenue, all time: **$9.83M** per DefiLlama, **$9.80M** rebuilt from wallet transfers
- Public Intents volume, all time through 2026-11-11, the last full day of the latest Dune reading: **$33.47B** per NearBlocks, **$33.09B** per NEAR's dashboard on Dune
- Chain Signatures: **16** MPC participants with a threshold of **11**
- Largest Intents fee channel, per NEAR's dashboard on Dune as read on 2026-11-12: **swapkit**, with **73%** of listed fees
- Bitwise NEAR ETF shares outstanding: **2,930,000** per the fund, **3,000,000** counted on chain in whole baskets
<!-- expected:end -->

## What's inside

| Area | Main tables in `gold` | Main sources |
|---|---|---|
| Chain usage, supply | `fct_chain_daily`, `fct_supply_daily`, `fct_circulating_supply_daily`, `fct_protocol_config`, `fct_contract_daily`, `fct_receiver_sample_daily` | NearBlocks, archival RPC, Neardata |
| NEAR Intents, revenue | `fct_intents_daily`, `fct_intents_chain_daily`, `fct_intents_asset_daily`, `fct_intents_fee_channels`, `fct_dune_intents_asset_daily`, `fct_dune_intents_chain_daily`, `fct_dune_intents_swaps_daily`, `fct_dune_intents_tvl_daily`, `fct_dune_intents_tvl_asset_daily`, `fct_dune_dashboard_results`, `fct_intents_1click_daily`, `fct_intents_1click_channel_daily`, `fct_revenue_capture` | DefiLlama, NearBlocks, revenue.near.org, NEAR's dashboard on Dune, Intents Explorer API |
| The Intents pool, on chain | `fct_intents_pool_chain_monthly`, `fct_token_price_daily` | Archival RPC, Coin Metrics, DefiLlama |
| Wallets | `fct_wallet_transfers`, `fct_wallet_counterparties`, `fct_revenue_inflows_daily`, `fct_wallet_balance_daily`, `fct_wallet_holdings`, `fct_token_holders`, `dim_entity` | FastNear, RPC, 1Click, Rhea |
| Security, staking | `fct_validator_summary`, `fct_chain_signatures_daily`, `fct_mpc_state`, `fct_lst_snapshot` | RPC, NearBlocks |
| Capital, DeFi | `fct_protocol_tvl_daily`, `fct_defi_tvl_daily`, `fct_exchange_balance_daily`, `fct_protocol_fees_snapshot`, `fct_stablecoin_assets`, `fct_yield_pools` | DefiLlama |
| Market, peers | `fct_market_daily`, `fct_token_prices`, `fct_peer_daily`, `fct_peer_supply_readings`, `fct_swap_services_daily` | CoinMetrics, Coinbase, DefiLlama, 1Click, Rhea |
| Bitwise NEAR ETF flows | `fct_etf_nrr_daily`, `fct_etf_nrr_chain_daily` | Bitwise's page, archival RPC, SoSoValue through news reports |
| Developers, governance | `fct_dev_activity_weekly`, `fct_repo_snapshot`, `fct_governance_proposals`, `fct_governance_decisions`, `fct_venear_snapshot`, `fct_governance_threads`, `dim_event` | GitHub, RPC, gov.near.org |
| Thesis models | `fct_thesis_scorecard`, `dim_claim`, `fct_net_dilution_daily`, `fct_deflation_scenarios`, `fct_intents_unit_economics_monthly`, `fct_intents_channel_economics_monthly`, `fct_intents_concentration_monthly`, `fct_valuation_multiples_daily`, `fct_usage_quality_daily`, `fct_usage_lead_correlations`, `fct_etf_absorption_daily` | The gold tables above, `registry/claims.csv`, `registry/issuance_scenarios.csv` |
| Data quality | `dq_reconciliation`, `dq_freshness`, `dq_revisions`, `dq_ingest_runs`, `dq_provenance` | All of the above |

Every table and column is described in [docs/DATA_CATALOG.md](docs/DATA_CATALOG.md), and the same guide is on the
dashboard at `site/docs/index.html`. Every table is also in `data/gold/` as Parquet, so you can read it without
building anything. How it fits together is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and what each source can
and can't tell you is in [docs/SOURCES.md](docs/SOURCES.md).
[docs/CIRCULATING_SUPPLY.md](docs/CIRCULATING_SUPPLY.md) explains how circulating supply is built from the lockup
contracts and what `market_cap_usd` means. [docs/README.md](docs/README.md) indexes the rest, defines the words this
project uses in a particular way, and says how to add a source, a table, a comparison, a claim or a question.

## Refresh the data

Run `make ingest`. See a status table with one line per dataset. It needs network access and can take about 90 minutes,
because it stays within free-tier limits and fills in history in batches. Keys in `.env` are optional and raise those
limits; copy `.env.example` to start. Without a key, a keyed source is skipped with a clear message.

Run `make backfill` for the long history jobs. They run in batches, so run it again for more; they can be stopped and
restarted.

A GitHub Action takes a snapshot every night on the `data/nightly` branch and rebuilds the dashboard's data and the
thesis with it. `main` stays on the date in `data/PINNED`, so the expected results above do not drift. Each commit on
that branch holds that night's code and data, so the same three steps rebuild it.

## NEAR technologies used

The warehouse reads NEAR directly through RPC and archival RPC, including contract views on `v1.signer` (Chain
Signatures), `intents.near` (NEAR Intents), `meta-pool.near`, `linear-protocol.near`, `lst.rhealab.near` and
`venear.dao` (House of Stake). It tracks NEAR Intents volume, fees and revenue, traces the revenue wallets named on
revenue.near.org, reads what the Intents contract held at every month end since it was deployed, and reads the Bitwise
NEAR ETF's holdings from its staking pool, `bitwise_2.poolv1.near`. No contract is deployed and no transaction is sent.

## Data

What is stored, where it came from, the terms it is held under and how to ask for something to be removed are in
[DATA_NOTICE.md](DATA_NOTICE.md). The [LICENSE](LICENSE) covers the code only; the data remains under each source's own
terms, listed in [registry/sources.csv](registry/sources.csv).

## Origin

This began as an entry in the Investment Thesis track of NEAR HACKATHON 2026. Prizes there are paid in NEAR, so the
author could gain exposure to the asset analysed here, and the thesis says so where it states its conclusion.

## Disclosures

- **Built during the hackathon window.** All code dates from 2026-10-29 or later. The first snapshot in `data/bronze`
  (2026-10-28) was imported from an earlier scaffold by the same author, `near-deflation-clock`, which is not a
  separate submission; `tools/import_legacy_snapshot.py` records how.
- **Libraries:** dbt-core, dbt-duckdb, DuckDB, requests and pytest, pinned in `requirements.lock`. The dashboard loads
  D3 and its fonts from a CDN.
- **AI assistance:** written with Claude Code.
- **Self-reported data:** figures from NEAR's own dashboard on Dune and from revenue.near.org are NEAR's reports about
  itself. Every table built from them says so, and [DATA_NOTICE.md](DATA_NOTICE.md) says how each reading was taken.
