# Data audit, 2026-11-05

An audit of the warehouse for integrity (does each table hold what it says, and is it right) and coverage (which questions of a long-term NEAR thesis it can answer, how deep, and with what independent check). Done against the pin of 2026-11-01 on `main`, then against the nightly snapshot of 2026-11-05, which this audit moved the pin to. Read it with [RECONCILIATION.md](RECONCILIATION.md), [SOURCES.md](SOURCES.md) and [USAGE_BREAK_2026-04-02.md](USAGE_BREAK_2026-04-02.md).

## In short

- **The foundations hold.** All 61 gold tables are unique on their stated grain, every column is documented with a unit, `make verify` passed 10/10 before and after this audit, and the strongest claims (issuance 2.48% against the 2.50% cap over the latest 30 days, treasury share 10%, wallet-based revenue within 0.3% of DefiLlama, supply matching the chain on every sampled day, prices within 0.1% across three sources) reproduce from committed data.
- **The nightly job had been red since 2026-11-04** because two reconciliation checks compared a hand-taken Dune reading from 11-01 against the revenue page's live cumulative totals, which drift about 0.3% a day past a 1% tolerance. Fixed: the checks now compare on the reading's last full day.
- **Nothing in the warehouse carries a live circulating supply.** NearBlocks' figure has read the same number since 2025-08-27, and CoinMetrics' market cap has equalled price times total supply since November 2025. Every `market_cap_usd` since then is fully diluted. Flagged by a new check and in the catalog; a real source is still needed.
- **DefiLlama's Intents volume changes meaning on 2026-09-01**, and the catalog said the opposite. Fixed in the documentation and held by two new checks.
- **`main` was missing data the nightly branch already had**: six empty 1Click tables, 2 validator epochs instead of 164, one receiver-sample day instead of 78, no fund-page readings for the ETF. Moving the pin to 2026-11-05 fixed that.
- **Smaller flaws fixed today:** wallet facts and GitHub weeks included a partial day or week; five registry tokens had no decimals, which emptied 200 holder rows; GitHub served a full year of zeros for anza-xyz/agave and gold took it as no activity; HSP-029 was still listed as voting after it passed; the accounts behind the April 2026 usage break were not in the registry.
- **The developer gas rebate removal has shipped.** The 2026-11-05 config read is the first with `contract_gas_reward_rate` 0 and protocol version 87. The burn model had applied today's rate to all of history, which at the new pin would have raised every past day's burn by 43%; it now uses the rate in force on each day.
- **Still open, in order of importance:** circulating supply, token metadata for holdings, and a fresh hand reading of the Dune dashboard.

Nothing from this audit is committed. The working tree holds the code changes, the moved pin and the regenerated docs; `git status` shows them.

## How it was checked

- Profiled every gold and silver table: row counts, date ranges, gaps in daily spines, null rates per column, duplicates on the stated grain, negative values, zero runs, stuck values and spikes against a trailing 30-day median.
- Ran cross-table sums the warehouse does not do itself: Intents volume by chain and by asset against the daily total, protocol TVL against chain TVL, market cap against price times supply, DefiLlama against NearBlocks and the revenue page month by month, the three sources' first and last days per peer chain.
- Compared `main` with the nightly snapshots of 11-03, 11-04 and 11-05, read the failed workflow logs, and read HSP-029's status from the 11-05 snapshot.
- Read five contracts' `ft_metadata` and tested the archival node's `validators` method by block height (it answers `VALIDATOR_INFO_UNAVAILABLE` at heights 100M and 130M, so by-height history is not a way around the `UNKNOWN_EPOCH` limit).
- Re-ran `make verify` at the 2026-11-01 pin before any change, after the code changes, and after the pin moved to 2026-11-05.

## Integrity findings

Ordered by how much they could mislead a reader of the thesis. Each ends with its status.

### 1. The nightly job failed on 2026-11-04 and 11-05 because of stale-reading checks

`gh run list` shows both scheduled runs red. Their logs show 8 of 10 checks passing, with `reconciliation gaps are explained` failing: one unexplained gap on 11-04, two on 11-05 (`intents_volume_all_time_page_vs_dune` at 1.385% and `intents_fees_all_time_page_vs_dune` at 1.366%, against a 1% tolerance). The Dune reading is a hand snapshot from 11-01 and cannot move, while the revenue page's cumulative totals grow about 0.3% a day, so these checks had to fail within days of any reading, and would have failed again after every future reading.

On the reading's last full day (10-31) the page's cumulative volume is 36,949,581,750 and the Dune tile 36,949,581,750: the tiles describe the day before the reading exactly. **Fixed:** `dq_reconciliation` now compares all-time tiles, TVL tiles and NearBlocks' cumulative with the other source on the reading's last full day. Both checks agree again (0.000% and 0.059%). The nightly stays red until this reaches `main`.

### 2. No live circulating supply, and market cap is fully diluted since November 2025

- `circulating_supply_near` in `fct_supply_daily` and `fct_market_daily` comes from NearBlocks `/v1/charts`. It has read 1,249,836,992 NEAR on every day from 2025-08-27 through 2026-11-04, and `/v1/stats` reports the same figure on 10-28, 11-01 and 11-05. The 431 days before 2025-08-27 moved every day.
- CoinMetrics' `CapMrktEstUSD` divided by `PriceUSD` tracked NearBlocks' figure until September 2025 (1,249.8M in both), moved to 1,256M in October, and has equalled total supply since November 2025 (1,280.0M against 1,280.1M; 1,310.4M against 1,310.5M on 10-31). `market_cap_usd` prefers CoinMetrics, so every value since then is price times total supply.
- Nothing documented this, and no check caught it, because the two sources were never compared with each other.

**Flagged:** a new check, `circulating_supply_latest_nearblocks_vs_coinmetrics`, differs by 4.6% with a written explanation; the catalog marks both columns; [SOURCES.md](SOURCES.md) records it. **Open:** a real circulating figure. The candidates are the lockup contracts read on chain, or the Foundation's published schedule.

### 3. DefiLlama's Intents volume changes meaning on 2026-09-01

Month by month, `volume_usd_defillama` equals NearBlocks' public-only figure from April to August 2026 (11.23B against 11.24B over those five months, 0.12% apart) and equals revenue.near.org's all-routes figure from September (4.80B in September and 3.99B in October, against NearBlocks' 3.68B and 2.46B). The revenue page's April to August total is 12.25B, 8.3% higher. Before April 2026 the three sources agree, so the step is invisible earlier. The catalog said DefiLlama "includes confidential Intents" throughout, which was wrong for five months, and `fct_peer_daily.dex_volume_usd` carries the same series.

**Fixed:** the catalog and SOURCES.md now say which figure the column follows and when; two new checks hold it (`intents_volume_2026_apr_aug_defillama_vs_nearblocks` agrees at 0.12%, `intents_volume_2026_apr_aug_defillama_vs_page` differs at 8.3% with an explanation). **Open:** why DefiLlama kept the old values is not confirmed; its adapter has no date rule.

### 4. `main` lacked data the nightly branch already held

At the 2026-11-01 pin, the six `fct_intents_1click_*` tables were empty (the Explorer key reached the nightly job after the pin), `fct_validator_summary` had 2 epochs, `fct_receiver_sample_daily` one day, `fct_venear_snapshot` one row, and four columns of `fct_etf_nrr_daily` (`volume_shares`, `fund_page_shares`, `staked_share`, `net_staking_rate`) were empty on every row because no fund-page snapshot predates the pin. The README listed these tables as if they were populated.

**Fixed by moving the pin to 2026-11-05.** Now: 1Click has 89 days from 2026-02-15 to 11-04 (daily from 2026-09-07, one day a week before that, so check which days are present before summing), 164 validator epochs from 2026-04-19 with the staking ratio between 40.8% and 47.8% and 335 to 435 validators, 78 receiver-sample days from 2026-08-19, four fund-page readings, 6 MPC and config snapshots, 5 veNEAR snapshots. The README's figures moved with the pin.

### 5. Wallet facts and GitHub weeks included a partial period

The convention is that daily series leave out the day a snapshot was taken on, and every daily series did, except the FastNear transfer crawl: `fct_wallet_transfers`, `fct_wallet_flows_daily` and `fct_revenue_inflows_daily` ran through the crawl day. At the 11-01 pin that added 6,214 NEAR of revenue inflows for a day that was 20 hours old, and it is why the README said $9.28M rebuilt from wallet transfers while the figure through 10-31 is $9.25M. `fct_dev_activity_weekly` likewise held the week that had started on the day of the read, with 9 commits across 18 repositories.

**Fixed:** transfers from the newest crawl's own day are left out until the next crawl (which re-reads that day in full, so nothing is lost), and a week is kept only once a read has seen it end. At the 11-05 pin the wallet figure is $9.41M against DefiLlama's $9.44M.

### 6. Five registry tokens had no decimals

`dim_token` took decimals only from 1Click's token list, which does not list USDT.e, USDC.e, LiNEAR, rNEAR or xRHEA. So `fct_token_holders` had no `amount_token` for the 200 LiNEAR and rNEAR rows out of 700, and `fct_wallet_holdings` could convert only tokens 1Click lists.

**Fixed:** `registry/tokens.csv` now carries `decimals` for all 12 tokens, read from each contract's `ft_metadata` on 2026-11-05 (USDT.e 6, USDC.e 6, LiNEAR 24, rNEAR 24, xRHEA 18; the other seven match 1Click). `dim_token` prefers the registry, and a new data test holds the registry to 1Click wherever both exist. All 3,500 holder rows now have amounts. **Open:** `fct_wallet_holdings` still converts only 65 of its 8,484 rows, because the tracked DEX and Intents contracts hold 7,852 distinct tokens with unknown decimals (`dclv2.ref-labs.near` alone holds 6,096). The table is unusable for "what do these accounts hold" until a metadata fetcher exists; see next steps.

### 7. GitHub served a year of zeros for anza-xyz/agave

`stats/commit_activity` returned HTTP 200 with 52 weeks of zero commits and `stats/contributors` returned `[]`, while the repository metadata says it was pushed to on 2026-11-01. Gold recorded Solana's reference client with no activity for a year, which would have made a peer comparison of developer activity wrong.

**Fixed:** a repository whose year of readings is all zero although it was pushed to in that year now has empty `commits` and `active_authors`, and the catalog says so. **Open:** fetching Agave's activity another way (the commits list or the GraphQL API).

### 8. HSP-029 and the April 2026 batch streams in the registry

- `registry/events.csv` still listed HSP-029 as `voting`. The 11-05 snapshot of `vote.dao` reads proposal 29 as `Timelock`, with about 3.29M veNEAR for and almost none against at 62% turnout. **Fixed:** the row says `happened`, and a 2026-11-02 event records the vote closing.
- The accounts that explain the 2026-04-02 break (`hotwallet.kaiching`, `users.kaiching`, `sweat-migration.near`, `relay.tg`, `0-relay.hot.tg`) were not in `registry/entities.csv`, so the warehouse could not subtract them and their per-account history sat only in a document. **Fixed:** they are registered with `track_contract_stats=1`. The nightly job fetches `contract_txns` for them once this change reaches `main`; NearBlocks' per-account window is 365 days, so April 2026 is capturable until about April 2027.

### 9. Burn used today's config for all of history, and the config changed on 2026-11-05

`fct_supply_daily.burn_near` was `gas_fee_near * (1 - contract_gas_reward_rate)` with the rate taken from the latest config snapshot and applied to every day since 2020. The 2026-11-05 snapshot is the first to read `contract_gas_reward_rate` 0 and `protocol_version` 87, against 0.3 and 86 on the five earlier reads: the developer gas rebate that vote.dao proposal 27 voted out on 2026-07-03 (91.6% turnout) has shipped. At the 11-05 pin, the old model silently raised the burn of every historical day by 43%, from 70% to 100% of gas.

**Fixed:** each day now uses the newest config read on or before that day, and days before the first read (2026-10-28) use the first read's rate, the 30% in force since mainnet launch; the rate used is exposed as `contract_gas_reward_rate`. Gas is about 1% of issuance, so the net-inflation figure barely moves, but the burn series is now right on both sides of the change. `protocol_reward_rate` still reads 0 while `treasury.near` receives 10% of issuance, so that field stays untrusted, and the 2026-11-05 change itself is worth confirming on a function-call receipt.

### 10. Sources restate their recent days, and DefiLlama can rewrite TVL history

`dq_revisions` is built from differences between snapshots, and with five nights visible it holds 3,344 rows:

| Series | Revised rows | Days touched | Median change | Largest change |
|---|---:|---:|---:|---:|
| DefiLlama chain TVL (all peers) | 2,087 | 1,843, back to 2021 | 0.19% | 11.4% |
| DefiLlama chain fees | 1,173 | 561 | 0.45% | 425% |
| DefiLlama stablecoins | 62 | 23 | 0.12% | 18.8% |
| DefiLlama Intents fees | 18 | 5 | 1.2% | 1,298% |
| revenue.near.org daily fees | 4 | 4 | 789% | 1,670% |
| NearBlocks, all series | 0 | 0 | | |

`dq_revisions` compares only a key's oldest and newest snapshot, so it shows that a value moved, not when. The rest of this finding compares each snapshot with the one before it, on the same 0.01% tolerance. NearBlocks has not restated anything.

**Fee and revenue days.** The NEAR family publishes a day's fees before the day's data has arrived, then rewrites it. A day's first read is the snapshot after it ends:

| Columns in `fct_intents_daily` | Days that moved | Last read that moved one |
|---|---|---|
| `fees_usd_revenue_page`, `fees_near_revenue_page` | 10-31, 11-01, 11-02, 11-03 | Second, one night after the first |
| `fees_usd_defillama` | 10-27, 10-31, 11-01, 11-02 | Third, two nights after the first |
| `revenue_usd_defillama`, `holders_revenue_usd_defillama` | 10-27, 10-31, 11-01, 11-02, 11-03 | Third |
| `supply_side_revenue_usd_defillama` | 10-31, 11-01, 11-02, 11-03 | Third |
| `treasury_revenue_usd_defillama`, and volume from all three sources | None | |

Three of the page's four first readings were 6% to 14% of the figure that followed ($11,755 then $125,254, $23,021 then $163,862, $9,319 then $164,920); the fourth was within 0.02%. DefiLlama follows a night later: at this pin it still reads $9,319 for 11-03, which also turns that day's supply-side revenue negative. No figure read three or more nights after its day has moved by more than 0.01%, though smaller moves come later ($0.36 on the page's 10-21, twelve nights after).

The evidence is thin. Only four days (10-29 to 11-01) have been read both on the third night and on the night after it. The move on 10-27 fell between the reads of 10-28 and 11-01, with no snapshot in between, so it may have come as late as the fifth night.

**Fixed:** `fct_intents_daily.is_fee_revenue_provisional` is true until a day's figures have been read three nights after the day ended, which marks the newest two days of a nightly build (11-03 and 11-04 at this pin). The number is `intents_fee_settle_nights` in `dbt_project.yml`. The data test `intents_fees_settle_when_the_flag_clears` fails if a figure moves in the day's first week after the flag clears, or if the flag disagrees with the reads. Later moves are rewrites of history, which `dq_revisions` lists and no trailing flag could predict.

`fct_peer_daily` carries the same flag, because NEAR's fees there are mostly Intents fees and move on the same reads (they read $33,285 for 10-31 and $146,822 two nights later, and $24,201 for 11-03 at this pin). The test `peer_fees_settle_when_the_flag_clears` holds the number for NEAR. The other six chains get the same rule so that a filter cuts every chain at the same day, not because they settle on that schedule. First reads of fees on Ethereum, Solana and Sui ran up to about 6% low; Ethereum's and Solana's figures also moved after the third read; and the 11-04 and 11-05 reads moved 165 and 557 of Solana's fee days, back to 2025-04-09, by up to 5.6%. Aptos and TON have not moved.

**TVL.** The table above reads as if DefiLlama's TVL moves every night, and this report first said so. It does not. The 11-03 read rewrote 2,079 Ethereum and Solana rows back to 2021 (median 0.19%, largest 11.4%), the 11-02 read moved 8 recent Aptos rows by 0.23%, and the 11-01, 11-04 and 11-05 reads moved nothing by more than 0.01%. NEAR's chain TVL and all 25 protocols on NEAR have not moved in any read. So a rewrite can come on any night, without notice, and a TVL chart reproduces only at a pin. **Fixed:** the catalog says so on `fct_peer_daily.tvl_usd` and `fct_protocol_tvl_daily`.

### 11. Smaller findings, documented or harmless

- `fct_chain_daily.multichain_txns` is 0 on all 717 days. Now documented; use `fct_chain_signatures_daily`.
- `dim_block_day.protocol_version` and `fct_supply_daily.protocol_version` are the block header's `latest_protocol_version`, the version the block's producer supports, not the version in force: it read 87 from the first block of 2026-11-04 while the config switched between the 11-04 and 11-05 reads. Now documented; the config snapshots date a change, the header field only announces it.
- `fct_protocol_tvl_daily` sums to 600.9M on 10-31 while DefiLlama's chain TVL is 197.5M: liquid staking, lending and bridges count the same NEAR up to three times. The model comment says so; never sum this table across protocols.
- `fct_peer_daily.fees_usd` for NEAR over the latest 30 days is $7.35M, of which NEAR Intents is $6.07M, Rhea $1.09M and gas $0.18M. A peer comparison of "fees" compares NEAR's cross-chain application fees, mostly paid to solvers and channels, with other chains' totals built the same way. State that in any chart.
- `fct_contract_daily` holds only days with activity: `sputnik-dao.near` has 365 rows across 1,066 days and `factory.bridge.near` ends on 2026-09-11. A missing day inside a window is a zero, and NearBlocks' limit of 365 is 365 active days.
- `fct_receiver_sample_daily` reads 96 blocks a day, about 0.12% of a day's blocks, so its estimates for bursty accounts are rough; `blocks_sampled` is on every row.
- `supply_side_revenue_usd_defillama` is negative on 4 days when a sweep exceeded the day's fees, and at this pin on 2026-11-03, because DefiLlama's fees for that day have not arrived (finding 10). Documented; sum it over weeks.
- `fct_supply_daily.minted_near` is negative on 79 days in 2020 (never more than 3 NEAR) and on 2023-12-01 (a 3,152 NEAR fall in total supply between two NearBlocks days). Harmless for any trailing mean; the plausibility test allows 0.5% a day.
- `fct_market_daily.price_usd` is empty for the first 84 days (2020-07-21 to 10-12), before any price source starts.
- `fct_wallet_flows_daily.amount_usd` exists for 799 of 2,921 native-NEAR rows, because FastNear values only some transfers. A USD estimate from the daily close would fill the rest.
- `fct_mpc_operators.tee_expiry` and `tee_image_hash` are empty on every row: NearBlocks has no attestation data, so the 2026-10-23 "entirely inside TEEs" claim is not checked here.
- `fct_wallet_counterparties` has two rows with no counterparty (protocol rewards to `treasury.near`, and `auroraliqsupport.near`'s own side).
- Carried over from `near-deflation-clock/docs/WAREHOUSE_AUDIT.md` and still open: the revenue page's monthly revenue runs $1.72M above the wallet-based figure (11.16M against 9.44M); 45,000 NEAR left `1csfundsadmin.sputnik-dao.near` for an unlabelled account on 2026-04-22; `treasury.near`'s 30M NEAR of outflows in April and May 2026 are unlabelled; the front-end fund holds 71,284 USDC unconverted; the 1-pip fee collector has no native account to follow.
- The only Dune reading was taken by an AI-driven browser on 2026-11-01 and its asset series ends on 10-31 (`dq_freshness` shows it 5 days behind). `registry/sources.csv` asks for it to be replaced by a reading taken by hand.
- Terms still to settle before the repository goes public: CoinMetrics (non-commercial), DefiLlama (republishing), NearBlocks (personal use), Bitwise (site content), Dune (hand readings only).

## Coverage, by thesis question

| Question | Tables | Depth at the 11-05 pin | Independent check | Gap |
|---|---|---|---|---|
| Supply, issuance, burn | `fct_supply_daily`, `fct_protocol_config`, `dim_block_day` | Daily from 2020-07-21; on-chain supply on 301 sampled days | NearBlocks vs archival RPC, 0.000% | No live circulating supply (finding 2); the 2026-11-05 rebate change rests on one config read (finding 9); no lockup or vesting schedule |
| Treasury | `fct_wallet_transfers`, `fct_supply_daily.treasury_reward_near` | Every transfer since 2020-10 | FastNear vs RPC vs NearBlocks balances within 0.5% | Outflows unlabelled |
| Intents revenue and fee switch | `fct_intents_daily`, `fct_revenue_inflows_daily`, `fct_revenue_capture`, `fct_intents_fee_channels` | Fees from 2025-05-06, revenue from 2025-09-22 | Wallet transfers vs DefiLlama, 0.3% | USDC fees and the buyback execution trail are not followed; revenue page monthly series unexplained; last two days provisional and flagged (finding 10) |
| Intents volume | `fct_intents_daily`, `fct_intents_chain_daily`, `fct_intents_asset_daily`, `fct_dune_intents_asset_daily`, `fct_intents_1click_*` | Public daily from 2025-10-29; all-routes from 2024-12-10; 1Click daily from 2026-09-07 | NearBlocks vs Dune public scope, 1.1% | Confidential volume is self-reported only; DefiLlama scope step (finding 3); Dune asset series ends 10-31 |
| Usage | `fct_chain_daily`, `fct_contract_daily`, `fct_receiver_sample_daily` | v1 daily from 2020; v3 daily for 369 days; 78 sample days | v1 vs v3 transactions, 0.000% | Levels break on 2026-04-02; batch-stream accounts now registered but not yet fetched; no retention or cohort data; sample is 0.12% of blocks |
| Security and staking | `fct_validator_summary`, `fct_validator_epoch`, `fct_mpc_state`, `fct_mpc_operators`, `fct_lst_snapshot` | 164 epochs from 2026-04-19; 6 MPC snapshots | NearBlocks operators vs contract, every snapshot | No validator history before April 2026; no TEE attestation; rNEAR staked amount empty |
| DeFi, TVL, stablecoins | `fct_protocol_tvl_daily`, `dim_protocol`, `fct_stablecoin_assets`, `fct_yield_pools`, `fct_peer_daily` | Protocol TVL from 2021-08-20; stablecoins from 2021 | DefiLlama vs NearBlocks TVL differ by definition, 62% | TVL double-counts across protocols; history can be rewritten on any night (finding 10); DefiLlama terms |
| Market | `fct_market_daily`, `fct_etf_nrr_daily`, `fct_etf_nrr_chain_daily` | Price from 2020-10-13, Coinbase from 2022-09; ETF from 2026-09-28 | Three price sources within 0.12%; ETF shares chain vs fund, 0.000% | Market cap fully diluted since 2025-11 (finding 2); no exchange flows or derivatives; ETF history before 11-02 partly estimated |
| Peers | `fct_peer_daily` | 7 chains; Ethereum from 2017 | Same source for all chains | TON has no market cap; NEAR "fees" are mostly Intents application fees; one source only |
| Developers | `fct_dev_activity_weekly`, `fct_repo_snapshot` | 18 repositories, 52 weeks | None | Agave unavailable (finding 7); fixed repository list, authors among the top 100 only |
| Governance | `fct_governance_proposals`, `fct_venear_snapshot`, `fct_governance_threads`, `dim_event` | 30 proposals; 5 veNEAR snapshots; 4 threads | None | No vote-level data; thread coverage is four topics |
| Ecosystem | `fct_catalog_projects` | 340 projects, point in time | None | No activity per project |

Not covered at all: holder distribution over time (top holders exist only per snapshot), exchange balances, lockups and vesting, bridge flows (DefiLlama's bridge API is paid), per-contract gas burn, account retention, stablecoin history per asset, DEX trade data, anything social.

## What changed today

Code and registry, all uncommitted:

| File | Change |
|---|---|
| `warehouse/models/gold/quality/dq_reconciliation.sql` | Dune-tile checks compare on the reading's last full day; three new checks: DefiLlama volume against NearBlocks and the page for April to August 2026, and circulating supply against CoinMetrics' implied supply |
| `registry/reconciliation_notes.csv` | Explanations for the two new gaps |
| `warehouse/models/silver/fastnear/stg_fastnear__transfers.sql` | The newest crawl's own day is left out |
| `warehouse/models/silver/ecosystem/stg_github__weekly_commits.sql` | The week in progress at a read is left out |
| `registry/tokens.csv`, `dbt_project.yml`, `warehouse/models/gold/core/dim_token.sql`, `warehouse/tests/token_decimals_match_oneclick.sql` | Decimals in the registry, preferred over 1Click, with a test holding the two together |
| `warehouse/models/gold/ecosystem/fct_dev_activity_weekly.sql` | A year of zeros for a repository pushed to in that year reads as unknown |
| `warehouse/models/gold/core/fct_supply_daily.sql` | Burn uses the contract reward rate in force on each day, exposed as `contract_gas_reward_rate` |
| `warehouse/models/gold/_gold.yml` | Descriptions corrected for DefiLlama volume, circulating supply, market cap, `multichain_txns`, `protocol_version`, supply-side revenue, burn, transfers, developer activity, decimals |
| `registry/events.csv` | HSP-029 passed; vote close recorded; the gas rebate removal shipping with protocol version 87 |
| `registry/entities.csv` | The five batch-stream and relayer accounts behind the April 2026 break |
| `docs/SOURCES.md` | Notes on NearBlocks circulating supply, DefiLlama volume scope, CoinMetrics market cap, Dune reading alignment |

Data: `data/` was replaced with the nightly branch's state at 2026-11-05 (`git checkout origin/data/nightly -- data`), which moved `data/PINNED` to 2026-11-05 and bronze from 483 files (9 MB) to 1,909 files (32 MB). `make warehouse fingerprints catalog verify` then regenerated the gold exports, fingerprints, catalog, reconciliation report and README figures.

Result: `make verify` passes 10/10 at the new pin, with 233 data tests (one more than before), 45 reconciliation checks (39 agree, 6 differ, each explained), 61 gold tables and 559 documented columns (one new: `fct_supply_daily.contract_gas_reward_rate`). The same code also passed 10/10 at the old 2026-11-01 pin before the data moved.

## What to do next

1. **Commit and push.** Until the reconciliation fix is on `main`, every nightly run stays red, and the nightly job keeps reading the old `registry/entities.csv`, so the batch-stream accounts are not fetched. Push also starts CI on the moved pin.
2. **A token-metadata fetcher** (`rpc/ft_metadata`): one `ft_metadata` call per token id seen in holdings or top holders, cached in `data/state`, so `fct_wallet_holdings` can value the thousands of tokens the DEX and Intents contracts hold, at least for the ones with a 1Click or Rhea price. Medium.
3. **Circulating supply.** Either read the lockup contracts on chain for a liquid-supply series, or take the Foundation's published schedule into the registry with a source URL. Until then, present `market_cap_usd` as fully diluted after 2025-10. Large, or small for the labelling alone.
4. **Confirm the rebate removal on chain**: read one function-call receipt from before and after 2026-11-05 and compare burnt gas with the fee charged. If the config is ever found to lag the chain, add a registry table of dated parameters with evidence. Small.
5. **Provisional marking** of the last days of the NEAR-family fee and revenue series, and a catalog note on DefiLlama TVL. Done (finding 10). Measure the nights again once `data/nightly` holds a few more weeks: the test catches a window that is too short, not one that is too long.
6. **A fresh Dune reading by hand**, following the steps in SOURCES.md, both to extend the asset series past 10-31 and to replace the AI-taken reading that `registry/sources.csv` asks to retire. User's hands only.
7. **Agave's commit history** by another route (the commits list with pagination, or the GraphQL API), and a general rule in the GitHub fetcher that a 200 with a year of zeros for a pushed-to repository is retried, not stored as fact. Small.
8. **Fill USD for native transfers** from the daily close where FastNear gives none, as a separate `amount_usd_estimated` column. Small.
9. **Label the treasury's counterparties** (`ecotreasury4/5.multisignature.near`, `foundation.near`, the implicit account that received 20.37M NEAR in May 2026) with evidence, so treasury outflows stop being a blank in the supply story. Research.
10. **Once the batch-stream accounts have a week of data**, add `txns_ex_batch_streams` and `active_accounts_v3_ex_batch_streams` to `fct_chain_daily` so usage can be shown on one comparable scale across 2026-04-02. Small, after the data arrives.
