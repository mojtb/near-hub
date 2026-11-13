# Redundancy audit, 2026-11-09

This audit asks two questions. Which DefiLlama and Dune figures does another source already give? Which columns in different gold tables carry the same value?

It was measured on `data/warehouse.duckdb` built at the 2026-11-08 pin: 64 gold tables, 608 columns. That pin is staged in the working tree but not committed. `data/PINNED` reads 2026-11-08, while `main` is at `793b096`, pinned to 2026-11-05. The first version of this report was measured at the 2026-11-05 pin, and the working tree moved to 11-08 minutes after its queries ran. Every identity it found still holds with three more nights. Section 6 lists what the first version got wrong. Nothing in the warehouse was changed. The queries were run by hand and are not part of `make verify`.

**Status, later on 2026-11-09:** the fixes are applied, under the rule chosen then: gold keeps one column per measure, and comparisons between sources live in `dq_reconciliation`. Section 7 lists every column that changed. Sections 1 to 6 describe the warehouse as it was before.

## 1. DefiLlama

DefiLlama runs 11 datasets a night, about 77 calls, which take 1.8 to 2.5 minutes of a 135 to 141-minute nightly run. `protocols` alone makes 26 calls and takes about a minute. Cutting calls therefore saves little time. The reasons to cut are meaning and licence, since DefiLlama's terms bar republishing.

- One dataset is fetched and never read.
- Three of the five Intents fee series are arithmetic of the other two.
- Intents volume and fees change scope during 2026, so neither can stand as a series. DefiLlama's volume still holds 29 days that nothing else has.
- DefiLlama's prices look poor only because our silver model misdates them. Once fixed, they are as good as any other source.

| Dataset | Calls | Gold columns | What else gives it | Verdict |
|---|---:|---|---|---|
| `chains` | 1 | None: no silver model reads `defillama__chains` | Nothing needed | Remove it, or use it for NEAR's TVL rank among all chains |
| `intents_fees`: `dailyHoldersRevenue`, `dailyProtocolRevenue`, `dailySupplySideRevenue` | 3 | `holders_`, `treasury_`, `supply_side_revenue_usd_defillama` | Arithmetic on all 698 days. Holders equals revenue from 2026-02-23, treasury equals revenue before it, and supply side equals fees minus revenue (68 days off by at most $1). `dim_date.is_fee_switch_active` holds the date | Remove the fetches and columns, and derive them in gold. The identity is DefiLlama's adapter rule today, so a change to that rule would go unseen |
| `intents_volume` | 1 | `volume_usd_defillama` | From 2026-09-01 it equals the revenue page on all 68 days. From 2026-04-01 to 08-31 it tracks NearBlocks' public count (143 of 153 days within 1%), while the page, which adds confidential routes, is up to 35% away. Before April 2026 it is within 1% of the page on 410 of 448 days. 29 days exist only here: 22 in December 2024 ($2.97M, which equals the base of the page's cumulative within 0.3%) and 7 between 2025-03-08 and 05-14 ($12.85M), which the page does not count at all, cumulative included | **Merge, don't drop.** Build one all-route series from the page, filled from DefiLlama on those 29 days, with a basis column. Public volume stays NearBlocks'. Keep DefiLlama's raw series for reconciliation |
| `intents_fees`: `dailyFees` | 1 | `fees_usd_defillama` | The revenue page. They agree within 0.1% on most days of January to March 2026 and from 2026-09-14. From 2026-04-01 to 09-13 DefiLlama counts public Intents only. It is lower on 152 of 153 days from April to August (monthly −1.6% to −4.9%), and the daily shortfall tracks confidential volume (correlation 0.76, about 5 bps of it). Its fees switch scope 13 days after its volume does. Only 5 days in May 2025, worth $8, exist only here | Read fees from the page, and keep DefiLlama's for reconciliation |
| `intents_fees`: `dailyRevenue` | 1 | `revenue_usd_defillama` | `fct_revenue_inflows_daily`, rebuilt from wallet transfers: $9,630,569 against $9,604,696 all time (0.27%). DefiLlama is the wallets' NEAR times the day's close (median 0.13%). FastNear values each transfer at its own time, so daily USD differs by 1.5% at the median and 0.8% by week. On a few days the NEAR itself differs: on 2026-07-14 DefiLlama counts about 7,300 NEAR more | Keep both: the figure the market quotes, and the independent one |
| `chain_fees` | 14 | `fct_peer_daily.fees_usd`, `revenue_usd`; `fct_protocol_fees_snapshot` | Nothing for the peers. NEAR's chain fee is 88% Intents fees and 2% gas, the rest mostly Rhea, over the last 90 settled days. The per-protocol snapshot is not a breakdown of the daily figure. Within the same read, its 24-hour sum is within 1% of the chain's last day on 4 of 9 reads and up to 20% off on the rest | Keep. The snapshot table is optional: its `near-intents` rows equal `fct_intents_daily`'s sums only in the read they came from, and silver keeps every read anyway |
| `chain_tvl` | 7 | `fct_peer_daily.tvl_usd` | None. Protocols sum to 3.0× NEAR's chain TVL, and NearBlocks' TVL is 0.35× to 0.38× of it | Keep |
| `chain_dex_volume` | 7 | `fct_peer_daily.dex_volume_usd` | None exactly. NEAR's DEX volume has been 79% to 95% Intents volume since May 2026. DefiLlama rewrote this history between the two pins (May 2026 down 1.1%) | Keep, and say that NEAR's DEX volume is mostly Intents |
| `stablecoin_chain`, `stablecoin_assets` | 8 | `fct_peer_daily.stablecoins_usd`; `fct_stablecoin_assets` | Nothing for the peers. For NEAR the chain comes within about 3%. `ft_total_supply` at the first block of 2026-11-08 gives USDC $92.6M (native $78.1M plus Rainbow-bridged $14.5M) against DefiLlama's $90.1M. It gives USDT $40.8M once the 489.0M unissued tokens at `tether-treasury.near` are left out, against $39.4M. DAI and FRAX are within 6.5% and 0.9% | Keep. A chain read for NEAR's row would be an independent check, not a replacement, because DefiLlama's exact exclusions are unknown |
| `peer_price` | 7 | `fct_peer_daily.price_usd` fallback; `fct_market_daily.price_usd_defillama` | CoinMetrics for six chains, nothing for TON. See below | **Keep, and fix our dating first** |
| `protocols`, `protocol_tvl` | 26 | `dim_protocol`, `fct_protocol_tvl_daily`, `fct_exchange_balance_daily` | Partly. Holdings valued in USD reach 92% of DefiLlama's near-intents plus confidential TVL, and come within 1.6% of `rhea-lend` and 11.6% of `rhea-dex`. That covers three protocols, from 2026-10-28 only. Exchange wallets are public: Bitfinex and KuCoin list their NEAR accounts in DefiLlama's open-source adapters, and Binance's adapter reads Binance's own proof-of-reserves address list. Their balances could be read from the chain. That is not built, and Binance's API answered HTTP 451 to this machine in earlier tests | Keep |
| `yield_pools` | 1 | `fct_yield_pools` | None for APY. It holds 10 pools in 3 projects. Only table lists read it: the README, `tools/catalog.py`, and a "planned" card in the site's design D | Optional drop |

**Our silver model misdates the prices; DefiLlama does not.** `stg_defillama__peer_price` dates a point by its timestamp minus one second. DefiLlama stamps its daily points near midnight, up to 2.4 hours either side, and 39% to 55% of each coin's points fall just after midnight. Those points land one day late. Two points then share a date, the tiebreak keeps the higher price, and the next day goes missing. Rounding each timestamp to the nearest midnight repairs it:

| Coin | Days missing now | Median gap to CoinMetrics now | 99th percentile now | Days missing after rounding | Median after rounding | 99th percentile after rounding |
|---|---:|---:|---:|---:|---:|---:|
| NEAR | 320 | 0.73% | 16.6% | 5 | 0.19% | 1.9% |
| Solana | 353 | 0.75% | 18.8% | 2 | 0.14% | 1.9% |
| Ethereum | 312 | 0.57% | 14.5% | 3 | 0.10% | 1.2% |
| Avalanche | 344 | 1.01% | 18.2% | 3 | 0.13% | 2.0% |
| Aptos | 271 | 0.34% | 13.7% | 0 | 0.12% | 1.0% |
| Sui | 239 | 0.42% | 14.0% | 0 | 0.14% | 1.0% |
| TON | 302 | no CoinMetrics series | | 3 | | |

The worst NEAR days show the mechanism. On 2026-06-04 DefiLlama's 2.8194 is CoinMetrics' close of the day before, 2.8250, not that day's 2.2012. TON's price in `fct_peer_daily` comes only from DefiLlama, so today half of its points are a day late and 302 days are missing. Sui's first 102 days, before CoinMetrics starts, are affected the same way. Once fixed, DefiLlama's NEAR price is about as close to CoinMetrics as NearBlocks' (0.14%) and Coinbase's (0.15%). It is also the natural fallback when NearBlocks' `/v1` stops on 2026-11-22. It is the main candidate if CoinMetrics' non-commercial licence rules CoinMetrics out.

`market_cap_usd_coinmetrics` is CoinMetrics' price times NearBlocks' circulating supply (median ratio 0.998 to 1.004 each year from 2021 to 2025), and it equals `fully_diluted_value_usd` in 2026. It is derivable and is kept only to tell the circulating-supply story.

**Who reads the DefiLlama columns proposed for change:**

| Column | Readers |
|---|---|
| `volume_usd_defillama` | Site `design-a.html` (the volume card) and `design-d.html` (6 places, including the take-rate chart), `_build/export_data.py`, Deflation Clock `models/warehouse.py`, `dq_reconciliation` |
| `fees_usd_defillama` | `design-a.html`, `design-d.html`, `export_data.py`, Deflation Clock `models/warehouse.py`, test `revenue_never_exceeds_fees_all_time`, `dq_reconciliation` |
| `holders_`, `treasury_`, `supply_side_revenue_usd_defillama` | Deflation Clock `models/warehouse.py` (lines 90, 91 and 184) and its test `tests/test_warehouse.py:47` |
| `price_usd_defillama` | `dq_reconciliation` |

The site's `shared/catalog.js` lists every column too, but `_build/export_catalog.py` regenerates it from the warehouse catalog. Designs A and D read DefiLlama's volume and fees together, so their take rate mixes scopes. It reads 13.8 bps in August 2026 against the page's 12.5, because public swaps pay more. It reads 11.8 bps from 09-01 to 09-13 against the page's 12.9, when DefiLlama's volume already counts confidential routes and its fees do not. From 09-14 the two agree.

## 2. Dune

Everything from Dune is one hand reading of 2026-11-01: 18 tiles, 100 fee channels and one widget, query 5175131 (2,541 rows, 2026-10-02 to 10-31).

| Gold table | Derivable elsewhere? | Evidence | Verdict |
|---|---|---|---|
| `fct_dune_dashboard_results` | Today, yes. It holds the same 2,541 rows as `fct_dune_intents_asset_daily` | The first reading captured one widget. The dashboard has at least seven queries (`registry/dune_queries.csv`), and this table is where the others land before they get a typed table | Keep |
| `fct_dune_intents_asset_daily` | The daily total, yes: it equals the revenue page on all 30 days. The split by asset across all routes, no | NearBlocks has each asset's public part: 64% of USDT, 54% of USDC, 77% of BTC (called NBTC there), 73% of ZEC, 69% of ETH, 19% of wNEAR. NearBlocks lists QTC ($51.8M here) and cNEAR without a dollar value. GRAM, USDG and PONS ($5.8M together) have no match by symbol | Keep |
| `fct_intents_dashboard_readings`, 18 tiles | 5 exactly, 1 within 0.13%, 10 roughly, 2 not at all | Exact: all-route volume all time, over 30 days, over 7 days and over the past day equals the page to the dollar, and confidential TVL equals the page. Near: all-route fees all time, $58.71M against the page's $58.79M. Rough: public volumes against NearBlocks (1.1% to 8.4%), confidential volumes as page minus NearBlocks (4.6% to 9.2%), public TVL against DefiLlama's near-intents TVL (10.0%), and all-route TVL (4.5%). Unique: the public and confidential fee split, $55.67M and $3.04M | Keep all 18 rows |
| `fct_intents_fee_channels`, 100 channels | No | The Explorer now covers 97 of the 100 referrals over 178 days since 2026-02-15, but only for 1Click: $22.7M of app fees against $57.3M listed (SwapKit $16.1M of $42.1M). 3 channels are Dune-only, $3.08M, nearly all of it "confidential intents" ($3.04M) | Keep |

The official API fetcher `dune/query_results` was skipped on all 7 runs for want of a key. No silver model reads its bronze, so a key alone would not bring anything to gold. The project wants all of the dashboard's data in the warehouse, so finishing it with a silver model or removing it is a decision, not a cleanup.

What Dune alone holds: all-route volume per asset, the public and confidential fee split, and all-time fees per channel. Every headline total it shows is also on revenue.near.org or NearBlocks.

## 3. Columns that carry the same value

### 3a. Exact copies

Zero rows differ unless stated.

| Value | Where it lives | Result at 11-08 | Owner |
|---|---|---|---|
| `total_supply_near` | `fct_supply_daily`, `fct_circulating_supply_daily`, `fct_validator_summary`, and the chain's figure as `onchain_supply_end_of_day_near` | Identical on 2,301, 233 and 730 rows. NearBlocks equals the chain on all 730 days the archival node was read | The chain (`dim_block_day`), because NearBlocks' figure comes from `/v1`, which ends on 2026-11-22 |
| `circulating_supply_near` | `fct_circulating_supply_daily`, `fct_supply_daily`, `fct_market_daily` | Identical | `fct_circulating_supply_daily` |
| `circulating_supply_near_nearblocks` | `fct_supply_daily`, `fct_market_daily` | Identical; frozen since 2025-08-27 | One table, as history |
| `circulating_share_of_total` | `fct_circulating_supply_daily`, `fct_market_daily` | Identical | Drop it from `fct_market_daily` |
| `gas_fee_near` | `fct_chain_daily`, `fct_supply_daily` | Identical, both from `/v1` | `fct_chain_daily`; 3c explains why `/v3` has no twin |
| `protocol_version` | `fct_supply_daily`, `dim_block_day` at D+1 | Identical | `dim_block_day` |
| `txns`, `txns_v1`, `txns_v3` | `fct_chain_daily` | v1 equals v3 on all 376 shared days | `txns` |
| `blocks` | `fct_chain_daily` | v1 equals v3 on all 372 shared days; already one column | As is |
| `txns` of `v1.signer` | `fct_chain_signatures_daily`, `fct_contract_daily` | Identical on 372 days. `signers` is not `unique_callers` (about 1.7% apart) | Keep one of the two counts |
| NearBlocks Intents totals | `fct_intents_daily` against sums and distinct counts of `fct_intents_asset_daily` and `fct_intents_chain_daily` | Identical on 371 days | The totals are a convenience |
| 1Click daily totals | `fct_intents_1click_daily` against `fct_intents_1click_channel_daily` | Identical. The pair, route and size tables are within $0.19 over 174 days | `senders` and `recipients` are its only columns of its own |
| Price columns of holdings | `fct_wallet_holdings` against `fct_token_prices` and `dim_token` | Identical on 68,189 rows | Denormalised by design |
| `price_usd`, `priced_on` | `dim_token` against the newest `fct_token_prices` row | Identical for the 8 tokens 1Click lists; empty for 4 Rhea-priced tokens | Join `fct_token_prices`. `coingecko_id` exists only in `dim_token` |
| NEAR's row | `fct_peer_daily` against `fct_market_daily` and `fct_intents_daily` | Price differs on one day (2020-10-14); cap and provisional flag identical | By design |
| MPC threshold and operators | `fct_mpc_operators` against `fct_mpc_state` and `fct_mpc_participants` | Agree on all 8 reads, including the drop to 15 operators and a threshold of 10 on 2026-11-07. NearBlocks' TEE fields are empty and `is_validator` is false on all 126 rows | `fct_mpc_operators` adds only `node_url` |
| `near-intents` rows | `fct_protocol_fees_snapshot` against sums of `fct_intents_daily` | Identical within the read they came from. By 11-08, later reads had raised the 11-05 read's 7-day fees by 12% | A first-read vintage, which silver already keeps |
| `gross_issuance_pct`, `net_issuance_pct`, `offset_pct` | `fct_revenue_page_emissions` | Arithmetic of the NEAR columns and `reference_supply_near` (within 0.018 points). The reference is one figure per read, the total supply at the end of the previous day, so every read moves every past day's percentage, by about 0.0001 points a night | Low stakes either way |
| `cumulative_revenue_usd`, `cumulative_revenue_near` | `fct_revenue_page_monthly` | Running sums | Drop |
| `cumulative_volume_usd_revenue_page`, `cumulative_volume_usd_nearblocks` | `fct_intents_daily` | Each day's step equals the daily column (661 and 374 days). The page's series starts from $2.96M, its December 2024. NearBlocks' starts from $2.87B, the history before its 365-day window, which equals the page's daily sum to 2025-10-28 within 0.24% | Keep NearBlocks'. The Deflation Clock reads it, and its base is history that no daily column holds |
| `txn_fee_usd`, `txn_volume_usd` | `fct_chain_daily` | The `/v1` NEAR amounts times NearBlocks' own price at the start of the day (median 0.03% and 0.000%) | Drop; they end with `/v1` |
| `market_cap_usd_coinmetrics` | `fct_market_daily` | See section 1 | Keep only for the story |
| `block_height` | `fct_etf_nrr_chain_daily` against `dim_block_day` at D+1 | Equal on 38 of 41 days. 3 differ by one or two blocks, because `dim_block_day` takes a block within 120 seconds after midnight, not always the first | As is |
| `balance_near_nearblocks` | `fct_wallet_balance_daily` against FastNear's running balance | Median gap 0, 99th percentile 0.004%, largest 0.02% over 933 days | A check |
| `balance_raw`, `amount_token` | `fct_token_holders` against `fct_wallet_holdings`, same account, token and night | 184 rows; 18 differ by 0.021% at the median, from two reads hours apart | As is |
| Labels copied from a dimension | Slug, name and category in `fct_protocol_tvl_daily` and `fct_exchange_balance_daily`; entity and category in `fct_contract_daily`, `fct_receiver_sample_daily` and `fct_wallet_transfers`; symbol in `fct_token_holders`; ecosystem and group in `fct_dev_activity_weekly` | Identical: each is built from the same registry or read | Convenience by design |

### 3b. Same name, different thing

These are not redundant. They need a rename or a line in the catalog.

| Name | Tables | Why they differ |
|---|---|---|
| `staked_near` | `dim_entity` against `fct_lst_snapshot` | `view_account`'s locked balance, 0 for every liquid-staking contract, against what the contract has delegated (21.6M for stNEAR). Rename one |
| `revenue_usd` | `fct_peer_daily` against `fct_revenue_page_monthly` | DefiLlama's chain revenue, 90% of it Intents, against NEAR's own monthly series. NEAR's series differs from the wallet inflows by 12% to 54% every month, and is $1.82M higher all time |
| `tvl_usd` | `fct_peer_daily`, `fct_protocol_tvl_daily`, `fct_yield_pools` | Chain, protocol and pool. Protocols sum to 3.0× the chain, and pools do not sum to their protocol |
| `volume_usd` | `fct_intents_asset_daily`, `fct_intents_chain_daily`, `fct_dune_intents_asset_daily`, `fct_intents_1click_daily` | Public only, all routes, and 1Click only (value paid in) |
| `swaps` | NearBlocks tables against 1Click tables | Public Intents swaps against 1Click swaps. `fct_intents_1click_daily` counts every status; the pair, route and size tables count finished swaps only |
| `fees_usd` | `fct_intents_fee_channels` against `fct_peer_daily` | All time per channel, against daily per chain |
| `price_usd` | `fct_market_daily`, `fct_peer_daily`, `fct_token_prices`, `dim_token`, `fct_wallet_holdings` | A day's close against a list price at read time. wrap.near on 1Click sits 0.04% to 4.4% from the previous close |
| `symbol` | `dim_token`, `fct_intents_asset_daily`, `fct_dune_intents_asset_daily`, `fct_stablecoin_assets`, `fct_yield_pools` | Display text, not a key: nBTC, NBTC and BTC; wNEAR and NEAR |
| `category` | `dim_entity` against `dim_protocol` and the protocol tables | The registry's group against DefiLlama's category |
| `status` | `dim_event`, `dq_ingest_runs`, `dq_reconciliation`, `fct_governance_proposals`, `fct_intents_1click_channel_daily` | Five vocabularies |
| `protocol_version` | `dim_block_day` against `fct_protocol_config` | The version a block's producer supports, which leads by a day, against the config in force |
| `read_on` | `dim_protocol` against `fct_governance_proposals` | The newest reading that listed the protocol, against the date of the reading |
| `block_height` | `dim_block_day`, `fct_etf_nrr_chain_daily`, `fct_wallet_transfers` | A block near the start of D, the first block of D+1, and the transfer's own block |
| `txns` | `fct_chain_daily`, `fct_contract_daily`, `fct_chain_signatures_daily` | Chain, contract, and signer contract. `fct_contract_daily.txns` carries the chain table's description ("v3 where available, else v1"), which is wrong for it |

### 3c. Same meaning, different source or definition

| Pair | Finding | What to do |
|---|---|---|
| `gas_price_yocto` in `fct_chain_daily` against `dim_block_day` | Equal on all 372 shared days only because the price sat at the floor all year: NearBlocks reports one value. One block at midnight and NearBlocks' daily figure would part under congestion | Keep one, and say which |
| `new_contracts` in `fct_chain_daily` | Built as v3 where it exists, else v1, but the two differ on 322 of 376 shared days, by 25% at the median. It is a splice with a definition change, like DefiLlama's volume | Split it into `_v1` and `_v3`, as `active_accounts` is |
| `txn_fee_near_v1` against `_v3`; `active_contracts_v1` against `_v3` | Identical except on 2026-04-15 (fees 648 against 732 NEAR, contracts 95,043 against 102,529) and by one contract on three days | One column each, v3 first |
| `active_accounts_v1` against `_v3` | v3 is 2.16× v1 at the median, because it adds relayed users | Keep both |
| `gas_fee_near` (v1) against `txn_fee_near_v3` | Not the same fee: v3's runs about 5% lower at the median (ratio 0.949) | v3 cannot replace v1 in `burn_near` after 2026-11-22 |
| `dim_protocol.near_tvl_usd` against the last day of `fct_protocol_tvl_daily` | 0% to 8.3% apart: read time against the previous close. 22 of the 47 protocols, 19 protocols and 3 exchanges, have no daily history | As is |
| `fees_near_revenue_page` against `fees_usd_revenue_page` divided by the close | 1.6% at the median, because NEAR converts at its own rate | As is |
| `emissions_ytd_near` against year-to-date `minted_near` | 0.27% at the median, so the two methods agree | Kept apart on purpose |
| NEAR's two year-to-date revenue series: `revenue_ytd_near` against the monthly series | Within −0.13% to 1.13%. Both run 12.6% above the wallets by 2026-10-31 | One would do; the wallets stay the check |
| ETF NEAR: `fct_etf_nrr_daily.near_in_trust` against `fct_etf_nrr_chain_daily.near_in_wallets` | Within 0.21% on 5 of 6 days. On 2026-11-03 they were 6.1% apart: a 180,000-share redemption showed on the fund page that day and reached the chain the next | Keep both: the chain settles a trading day later and nets orders |
| ETF shares: `shares_outstanding` against `running_settled_shares` | Equal the next day on 20 of 29 days, and the same day on 8 | Keep both, by design |
| GitHub's commit statistic against the default-branch count | 0.65× to 1.80× by repository, and equal every week for 6 of 18. The statistic is empty for Agave | Compare repositories with the default-branch count; the statistic is optional |
| `amount_usd` against `amount_usd_estimated` | The estimate equals FastNear's value on all 7,437 transfers FastNear valued, and adds 4,134 more; 486 have neither. `fct_revenue_inflows_daily` (2 rows without USD) and `fct_wallet_counterparties` use FastNear's value alone | Merge into one `amount_usd` with `usd_basis`, and let both tables use it |
| Native NEAR in `fct_wallet_holdings` against `dim_entity` (RPC) and `fct_wallet_balance_daily` (crawl) | Within 0.03% for most accounts, and 3% for meta-pool.near, read hours apart. treasury.near is the exception: holdings say 47.76 NEAR on all 8 reads, while RPC and the crawl say 1.59M | See section 5 |
| LST prices: `fct_token_prices` against each contract's rate times wrap.near's price | 0.04% to 0.49% at 11-08 | Kept as a check in `dq_reconciliation` |

Columns computed inside one table from its neighbours are conveniences, not copies of a fact, and are not listed. Examples are shares, ranks, running totals, `fully_diluted_value_usd` and `turnout`.

## 4. How to merge

In order of value:

1. **Fix the price dating** in `stg_defillama__peer_price`: round each timestamp to the nearest midnight before taking the day. This repairs TON's peer price, Sui's first 102 days and `price_usd_defillama`. Then keep DefiLlama's prices for every coin.
2. **Make the chain or `/v3` the owner wherever `/v1` is the source.** NearBlocks switches `/v1` and `/v2` off on 2026-11-22, per its migration guide as read on 2026-11-08. Total supply and the circulating-supply day spine move to `dim_block_day`, which is daily from 2025-01. `txns`, `blocks`, transaction fees and active contracts move to v3. `price_usd_nearblocks` can move to `/v3` price stats, which the nightly job already fetches but no model reads. These have no `/v3` twin here and stop on that date: `gas_fee_near`, and with it `burn_near` and `minted_near`; `new_accounts`, `deleted_accounts`, `unique_contracts`, `gas_used`, `multichain_txns` and `active_accounts_v1`; `txn_fee_usd` and `txn_volume_usd`. `burn_near` feeds the Deflation Clock, so it needs a new source before then.
3. **Intents volume:** one all-route series from the page, filled from DefiLlama on its 29 extra days, with a basis column. Public volume comes from NearBlocks, and DefiLlama's raw series stays only in `dq_reconciliation`. Update designs A and D, `export_data.py`, the Clock and the six reconciliation lines.
4. **Intents fees:** read from the page, with DefiLlama's only in reconciliation. Drop the three derived series and their fetches. The Clock's buyback becomes revenue where `is_fee_switch_active` holds, and its test moves with it. Point `revenue_never_exceeds_fees_all_time` and the provisional rule at the page's fees.
5. **Intents revenue:** keep DefiLlama's and the wallets' side by side.
6. **Dune:** keep all four tables, and decide whether to finish or remove the API fetcher.
7. **Transfer USD:** one `amount_usd` with `usd_basis`, used by `fct_revenue_inflows_daily` and `fct_wallet_counterparties` too.
8. **Native NEAR in holdings:** take it from RPC `view_account` for tracked accounts, or mark FastNear's value. Section 5 explains why.
9. **Small cuts:** `dim_token`'s price columns; `fct_mpc_operators` down to `node_url`; one of the two `v1.signer` counts; the `near-intents` rows of `fct_protocol_fees_snapshot`; the page's three percentages; the monthly running totals.
10. **Renames:** `dim_entity.staked_near` to `locked_for_staking_near`, or `fct_lst_snapshot.staked_near` to `delegated_near`. Fix the description of `fct_contract_daily.txns`.
11. **Independent checks worth adding**, not replacements: NEAR's stablecoins from `ft_total_supply` less issuer treasuries (within 3% today), and exchange balances read from the public wallet lists.

Each change moves fingerprints, the catalog and the site's catalog. Run `make warehouse fingerprints catalog verify`, then the site's `export_data.py` and `export_catalog.py`, then the Clock's `make import-warehouse`.

## 5. Problems found on the way

- **Our silver model misdates DefiLlama's prices** (section 1). TON's price in `fct_peer_daily` is affected on every day it has.
- **`fct_wallet_holdings` says treasury.near holds 47.76 NEAR.** RPC says 1,593,768, and the transfer crawl agrees. FastNear's `/v1/account/{id}/full` returned the same 47.76 on all 8 reads, so its account state appears not to apply the epoch rewards the treasury receives. The treasury's holdings value reads $177 instead of about $5.9M.
- **DefiLlama's Intents fees count public routes only from 2026-04-01 to 09-13**, 13 days longer than its volume does.
- **NEAR's own volume series lacks 7 days** between 2025-03-08 and 05-14 that DefiLlama has, worth $12.85M. Its cumulative skips them too.
- **`fct_chain_daily.new_contracts` splices v3 onto v1**, although the two differ by 25% at the median.
- **NearBlocks `/v1` ends on 2026-11-22**, and the warehouse's daily gas fee, burn and minted series end with it.
- **revenue.near.org rewrites every past percentage on each read**, by about 0.0001 points, because its reference supply is the newest total supply.
- **DefiLlama rewrote NEAR's DEX volume history** between the 11-05 and 11-08 reads (May 2026 down 1.1%). This is another case of its history moving without notice.
- **NearBlocks v1 and v3 disagree on 2026-04-15 alone**, for transaction fees (11.6%) and active contracts (7.3%).

## 6. What the first version got wrong

1. **It was measured at the 2026-11-05 pin.** The working tree moved to 2026-11-08 after its queries ran. All numbers here are at 11-08, and every identity held.
2. **"DefiLlama's NEAR price is the weakest source" was wrong.** The gaps and the 320 missing days come from our dating bug, and the advice to drop the price is reversed.
3. **"wNEAR appears only on Dune" was wrong.** My query renamed NearBlocks' wNEAR to NEAR before matching. NearBlocks holds 19% of it.
4. **"The page's cumulative is $2.997B on 2025-01-01" misread the output by a factor of a thousand.** It is $3.0M.
5. **"One day 90% apart (2026-07-14)" joined two different days.** The 90% day is a near-zero day (2026-04-22), and 07-14 is 43% apart. "The NEAR amounts agree" was an inference; it is now measured at 0.13%.
6. **DefiLlama's fees were called a stale copy "on every day of April to August".** They are a scope change that lasts through 2026-09-13. They are lower on 152 of 153 days, with monthly gaps of 1.6% to 4.9%.
7. **"The per-protocol 24-hour sum equals the chain figure, 0.99 to 1.01" compared different reads.** Within the same read it holds on 4 of 9 reads.
8. **"The `near-intents` rows equal the daily sums"** holds only within the read they came from.
9. **"31 of 47 protocols have no daily history" forgot the exchanges.** The figure is 22.
10. **The tile count said 9 approximate and "7 new".** It is 10 approximate and 2 unique, and the confidential volumes are 4.6% to 9.2% off, not 9% to 10%.
11. **"12 datasets" is 11.**
12. **`gas_price_yocto` was listed as an exact copy.** It is equal only while gas sits at the floor.
13. **`dim_token.coingecko_id` was listed as a copy.** Nothing else holds it.
14. **`fct_mpc_operators` was to be kept for `is_validator`**, which is false on every row.
15. **Recommendations changed.** Keep `fct_dune_dashboard_results`. Treat the Dune API fetcher as a decision. Merge DefiLlama's volume rather than drop it. Make the chain or `/v3` the owner of `/v1` columns.
16. **The consumer list was incomplete.** Site designs A and D, the Clock's test, `README.md` and `tools/catalog.py` read some of the columns or tables.
17. **Pairs were missing:** the ETF's NEAR and shares, the two commit measures, the two transfer USD columns, native NEAR across three tables, NEAR's two year-to-date revenue series, LST prices and the copied labels.
18. **"Nothing outside DefiLlama" for NEAR's stablecoins and exchange wallets was too strong.** The chain comes within 3% for the first, and the wallet lists are public for the second.

## 7. What was changed

Applied on 2026-11-09, then rebuilt on that day's nightly data at the 2026-11-09 pin, uncommitted. `make verify` passes 10 of 10: 291 data tests, 98 unit tests, 64 gold tables and 564 documented columns, down from 608. `dq_reconciliation` has 77 checks, 68 agree and 9 differ, each with a written explanation.

**The rule.** A gold table holds each measure once. Where several sources measure the same thing, gold takes one, joining sources only where they agree day for day or naming each day's source in a `_basis` column. Where two sources count different things, both stay under names that say what each counts. `dq_reconciliation` reads the other sources from silver. Six checks were added for comparisons gold no longer shows: NearBlocks /v1 against /v3 for transaction fees, gas fees and active contracts, the two NearBlocks counts of v1.signer transactions, the MPC threshold, and GitHub's statistic against the default-branch count for near/nearcore.

**Fixes.**
- DefiLlama prices are dated by the nearest midnight. TON's peer price now covers all but 3 days of its span, against 302 missing before.
- Native NEAR in `fct_wallet_holdings` is the RPC balance read the same night: treasury.near reads about 1.59M NEAR, no longer 47.76.
- Total supply, gas fees, gas used and NearBlocks' price come from /v3 first, so they continue after /v1 is switched off on 2026-11-22.
- `defillama/chains` and the three derived Intents fee series are no longer fetched.
- `dune/query_results` has a silver model, so an API key's results reach `fct_dune_dashboard_results`, marked `read_via = 'api'`.

**Columns that changed.**

| Table | Was | Now |
|---|---|---|
| `fct_intents_daily` | `volume_usd_revenue_page`, `volume_usd_defillama` | `volume_usd`, all routes, with `volume_basis` |
| | `fees_usd_revenue_page`, `fees_usd_defillama`, `fees_near_revenue_page` | `fees_usd`, all routes, with `fees_basis` |
| | `revenue_usd_defillama` | `revenue_usd` |
| | `holders_`, `treasury_`, `supply_side_revenue_usd_defillama` | removed: `revenue_usd` split at `dim_date.is_fee_switch_active`, and `fees_usd` minus `revenue_usd` |
| | `volume_usd_nearblocks`, `cumulative_volume_usd_nearblocks` | `public_volume_usd`, `public_volume_cumulative_usd` |
| | `swaps_`, `accounts_`, `tokens_`, `chains_nearblocks` | `public_swaps`, `public_accounts`, `public_tokens`, `public_chains` |
| | `cumulative_volume_usd_revenue_page` | removed: the running sum of `volume_usd` |
| `fct_chain_daily` | `txns_v1`, `txns_v3` | `txns` |
| | `active_accounts_v1`, `active_accounts_v3` | `active_signers`, `active_accounts_with_relayed` |
| | `active_contracts_v1`, `_v3`; `txn_fee_near_v1`, `_v3` | `active_contracts`; `txn_fee_near` |
| | `new_contracts` | `new_contracts_v1` and `new_contracts_v3`, two counts 25% apart |
| | `txn_fee_usd`, `txn_volume_usd`, `multichain_txns` | removed |
| `fct_supply_daily` | `circulating_supply_near`, `circulating_supply_near_nearblocks`, `onchain_supply_end_of_day_near`, `protocol_version`, `gas_fee_near` | removed: in `fct_circulating_supply_daily`, `dq_reconciliation`, `dim_block_day` and `fct_chain_daily` |
| `fct_circulating_supply_daily` | `total_supply_near` | removed: in `fct_supply_daily` |
| `fct_market_daily` | price per source, CoinMetrics' market cap, Coinbase's open, high, low and volume, three circulating-supply columns | removed; `price_basis` added |
| `fct_peer_daily` | | `price_basis` added |
| `fct_wallet_transfers`, `fct_wallet_flows_daily` | `amount_usd`, `amount_usd_estimated` | `amount_usd`, FastNear's value else the day's close, with `usd_basis` on transfers |
| `fct_wallet_balance_daily` | `balance_near_nearblocks` | removed |
| `fct_wallet_holdings` | `price_usd`, `price_source`, `price_date`, `price_depth_usd` | removed: join `fct_token_prices` |
| `dim_token` | `price_usd`, `priced_on` | removed |
| `dim_entity`, `fct_lst_snapshot` | `staked_near` in both | `locked_near` and `delegated_near` |
| `fct_validator_summary`, `fct_mpc_operators` | `total_supply_near`; `threshold` | removed |
| `fct_revenue_page_emissions`, `fct_revenue_page_monthly` | the page's three percentages; its two running totals | removed |
| `fct_dev_activity_weekly` | `commits`, `active_authors` | removed: GitHub's statistic stays in silver |
| `fct_dune_dashboard_results` | | `read_via` added |

**The 2026-11-09 nightly.** It ran the code on `main`, without these changes, and brought two problems.
- The Bitwise ETF page parse failed: the market-price chart had a null for 2026-11-05, and rounding it raised an error. The parser now leaves out a chart day that has not been filled yet, a unit test holds that, and the night's reading was fetched again and stored under its own snapshot date, so the share count of 3,000,000 as of 2026-11-06 is kept.
- Public Intents volume fell from 2026-11-03, to between 0.4% and 18% of all routes, while all-route volume held. This was first read as a NearBlocks outage, because 1Click's swaps exceeded all public volume. NEAR's own dashboard on Dune shows the same fall, so the fall is real: almost all volume now settles confidentially, 1Click's included, and 1Click's route fields describe the user's legs, not settlement. The check built on the outage reading was replaced by `intents_volume_30d_nearblocks_vs_dune_public`, which compares NearBlocks with NEAR's own public figure.

**Kept on purpose.** Labels copied from a dimension (entity, category, symbol, slug), NEAR's row in `fct_peer_daily`, daily totals beside their breakdowns, `fct_chain_signatures_daily.txns` beside `fct_contract_daily`'s count for v1.signer, and the ETF's fund-reported and chain-settled figures. Each is either an attribute rather than a measure, a different grain, or a different thing measured, and the reconciliation or a test holds the pairs that should match.

**Consumers.** The site's `export_data.py` reads the new names under the same data keys, `shared/data.js` and `shared/catalog.js` were rebuilt, and the SQL shown in designs A and D names the new columns. The Deflation Clock's loader reads the new names and still reads its committed import of 2026-11-05. Its data folder was not re-imported: running `make import-warehouse` moves it to all-route volume, so its README and THESIS numbers need a refresh then.

