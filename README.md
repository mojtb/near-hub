# near-thesis

A reproducible data warehouse for a long-term investment thesis on NEAR, built for the Investment Thesis track of NEAR HACKATHON 2026. It collects public on-chain, protocol, wallet and market data into one tested, documented set of tables that anyone can rebuild.

**Status:** this is step 1 of the entry. The warehouse is here. Metrics, dashboards and `THESIS.md` come next and will be built on these tables. The repository makes no investment claim yet.

## The problem

Evidence about NEAR is scattered across a dozen services, and they disagree. Active accounts differ by 1.8x between two versions of one API today, and differed by 9x to 18x before April 2026. Some "independent" sources read the same NEAR-uploaded dataset. Price series are stamped a day apart. Free tiers and endpoints change or disappear. A thesis built on that is hard to check and easy to fool yourself with.

This warehouse keeps every raw response, types it, joins it into shared tables, and publishes where sources disagree instead of picking the convenient number.

## Try it

You need Python 3.11 and `make`. No keys and no API calls are needed for these steps; `make setup` downloads the Python packages.

1. Run `make setup`. See `Setup complete: N packages installed`.
2. Run `make warehouse`. See `Warehouse built as of ...`, in under a minute. This rebuilds `data/warehouse.duckdb` and `data/gold/` from the raw responses committed in `data/bronze/`.
3. Run `make verify`. See `10/10 checks passed`. This re-hashes every raw file, runs the data and unit tests, and confirms each gold table reproduces its committed fingerprint.
4. Run `make query SQL="select check_id, value_a, value_b, status from gold.dq_reconciliation order by status, check_id"`. See each comparison between sources.
5. Open [docs/RECONCILIATION.md](docs/RECONCILIATION.md). See where sources agree, where they don't, and why.

If you prefer a container, run `docker build -t near-thesis . && docker run --rm near-thesis`. See the same `10/10 checks passed`.

### Expected results

These lines are generated from the warehouse, and `make verify` fails if they stop matching it.

<!-- expected:start -->
- Data through: **2026-11-07**, the last full UTC day before the pinned snapshot of 2026-11-08; `dq_freshness` lists any source that ends earlier
- Gold tables and columns: **64** and **608**
- Reconciliation: **61** comparisons agree, **9** differ, each with a written explanation
- Issuance over the last 30 days, from supply change plus burn: **2.50%** a year, against **2.50%** in the protocol config
- Circulating supply, built from NEAR's lockup contracts: **1,308.99M** NEAR, **99.84%** of total supply; on 2025-08-26, the last day NearBlocks computed its own, **1,249.72M** against **1,249.65M**
- Captured Intents revenue, all time: **$9.63M** per DefiLlama, **$9.60M** rebuilt from wallet transfers
- Public Intents volume, all time through 2026-10-31, the last full day of the latest Dune reading: **$33.30B** per NearBlocks, **$32.93B** per NEAR's dashboard on Dune
- Chain Signatures: **15** MPC participants with a threshold of **10**
- Largest Intents fee channel, per NEAR's dashboard on Dune as read on 2026-11-01: **swapkit**, with **73%** of listed fees
- Bitwise NEAR ETF shares outstanding: **3,000,000** per the fund, **3,000,000** counted on chain in whole baskets
<!-- expected:end -->

## What's inside

| Area | Main tables in `gold` | Main sources |
|---|---|---|
| Chain usage, supply | `fct_chain_daily`, `fct_supply_daily`, `fct_circulating_supply_daily`, `fct_protocol_config`, `fct_contract_daily`, `fct_receiver_sample_daily` | NearBlocks, archival RPC, Neardata |
| NEAR Intents, revenue | `fct_intents_daily`, `fct_intents_chain_daily`, `fct_intents_asset_daily`, `fct_intents_fee_channels`, `fct_dune_intents_asset_daily`, `fct_dune_dashboard_results`, `fct_intents_1click_daily`, `fct_intents_1click_channel_daily`, `fct_revenue_capture` | DefiLlama, NearBlocks, revenue.near.org, NEAR's dashboard on Dune, Intents Explorer API |
| Wallets | `fct_wallet_transfers`, `fct_wallet_counterparties`, `fct_revenue_inflows_daily`, `fct_wallet_balance_daily`, `fct_wallet_holdings`, `fct_token_holders`, `dim_entity` | FastNear, RPC, 1Click, Rhea |
| Security, staking | `fct_validator_summary`, `fct_chain_signatures_daily`, `fct_mpc_state`, `fct_lst_snapshot` | RPC, NearBlocks |
| Capital, DeFi | `fct_protocol_tvl_daily`, `fct_exchange_balance_daily`, `fct_protocol_fees_snapshot`, `fct_stablecoin_assets`, `fct_yield_pools` | DefiLlama |
| Market, peers | `fct_market_daily`, `fct_token_prices`, `fct_peer_daily` | CoinMetrics, Coinbase, DefiLlama, 1Click, Rhea |
| Bitwise NEAR ETF flows | `fct_etf_nrr_daily`, `fct_etf_nrr_chain_daily` | Bitwise's page, archival RPC, SoSoValue through news reports |
| Developers, governance | `fct_dev_activity_weekly`, `fct_repo_snapshot`, `fct_governance_proposals`, `fct_venear_snapshot`, `fct_governance_threads`, `dim_event` | GitHub, RPC, gov.near.org |
| Data quality | `dq_reconciliation`, `dq_freshness`, `dq_revisions`, `dq_ingest_runs`, `dq_provenance` | All of the above |

Every table and column is described in [docs/DATA_CATALOG.md](docs/DATA_CATALOG.md). Every table is also in `data/gold/` as Parquet, so you can read it without building anything. How it fits together is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), and what each source can and can't tell you is in [docs/SOURCES.md](docs/SOURCES.md). [docs/CIRCULATING_SUPPLY.md](docs/CIRCULATING_SUPPLY.md) explains how circulating supply is built from the lockup contracts and what `market_cap_usd` means.

## Refresh the data

Run `make ingest`. See a status table with one line per dataset. It needs network access and can take about 90 minutes, because it stays within free-tier limits and fills in history in batches. Keys in `.env` are optional and raise those limits; copy `.env.example` to start. Without a key, a keyed source is skipped with a clear message.

Run `make backfill` for the long history jobs. They run in batches, so run it again for more; they can be stopped and restarted.

A GitHub Action takes a snapshot every night on the `data/nightly` branch. `main` stays on the date in `data/PINNED`, so the expected results above do not drift. Each commit on that branch holds that night's code and data, so the same three steps rebuild it.

## NEAR technologies used

The warehouse reads NEAR directly through RPC and archival RPC, including contract views on `v1.signer` (Chain Signatures), `intents.near` (NEAR Intents), `meta-pool.near`, `linear-protocol.near`, `lst.rhealab.near` and `venear.dao` (House of Stake). It tracks NEAR Intents volume, fees and fee capture, traces the revenue wallets named on revenue.near.org, and reads the Bitwise NEAR ETF's holdings from its staking pool, `bitwise_2.poolv1.near`. No contract is deployed and no transaction is sent.

## Disclosures

- **Built during the hackathon window.** All code dates from 2026-10-29 or later. The first snapshot in `data/bronze` (2026-10-28) was imported from an earlier scaffold by the same author, `near-deflation-clock`, which is not a separate submission; `tools/import_legacy_snapshot.py` records how.
- **Libraries:** dbt-core, dbt-duckdb, DuckDB, requests and pytest, pinned in `requirements.lock`.
- **AI assistance:** written with Claude Code.
- **Data:** this repository's MIT license covers code only. Data remains under each source's terms, listed in [registry/sources.csv](registry/sources.csv).
- **Data derived from Dune:** everything in `data/bronze/dune_public`, and every gold table with a `derived_from` column, comes from the [NEAR Intents dashboard](https://dune.com/near/near-intents) on Dune, created by @near. NEAR uploads the data behind it, so these numbers are self-reported. Readings are taken by hand in a browser and never on a schedule, with one exception: the first reading, in `near_intents_dashboard`, was taken by an AI-driven browser at the author's request. The manifest says how each was read.
- **Bitwise NEAR ETF data:** figures and the wallet list come from [Bitwise's page](https://nrretf.com), whose terms limit copying site content, so the page itself is not stored. Flows before the first saved snapshot come from `registry/etf_nrr_history.csv`, and some of them are estimates; each row says how it was reached.

## Data credits

NearBlocks, DefiLlama, FastNear, Neardata, revenue.near.org, Coin Metrics (community data, [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)), Coinbase, 1Click, Rhea, Meta Pool, GitHub, NEAR Catalog, gov.near.org, the [NEAR Intents dashboard](https://dune.com/near/near-intents) by @near on Dune, Bitwise, and SoSoValue through the news reports linked in `registry/etf_nrr_history.csv`.
