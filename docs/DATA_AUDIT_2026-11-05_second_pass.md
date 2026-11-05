# Data audit, second pass, 2026-11-05

A second look at the warehouse later on the same day as [DATA_AUDIT_2026-11-05.md](DATA_AUDIT_2026-11-05.md), after that audit's fixes and the four branches that followed it (circulating supply from the lockup contracts, token metadata and USD values for holdings, provisional fee days, one slug per protocol) had all been merged as `02dc49e`. Same two questions: does each table hold what it says, and which questions of a long-term NEAR thesis can it answer. Read it with [RECONCILIATION.md](RECONCILIATION.md), [SOURCES.md](SOURCES.md) and [CIRCULATING_SUPPLY.md](CIRCULATING_SUPPLY.md).

## In short

- **The state found was sound.** All 63 gold tables were unique on their stated grain, every column documented with a unit, 278 data tests and 95 unit tests passing, `make verify` 10/10 on a clean clone, the reproducibility CI green on both pushes of the day, and 61 of 70 reconciliation comparisons agreeing, each gap explained. The scheduled nightly job had still not run with the repaired Dune checks, so its first green run is expected on 2026-11-06.
- **The largest gap was one the warehouse could already close.** `fct_wallet_holdings` carried a USD value on 65 of 8,484 rows at the pin because 5,261 rows had a price but no decimals, while the price lists that priced them carry decimals of their own. Those decimals now stand in until a token's contract is asked: 970 rows valued, $641.3M, and the Intents holdings check that was `not_available` now agrees at 5.8%.
- **Four things said more than the data held.** The validator tables are a daily sample of epochs, not every epoch; `week_start` in developer activity was called Monday and is Sunday; exchange balances were listed as "not covered at all" while DefiLlama's exchange wallets sat in silver; and GitHub's own weekly statistic turns out to count differently from the default branch, by a quarter for nearcore, which no reader could see. All four are fixed in the tables or their descriptions.
- **Agave has numbers.** GitHub serves a year of zeros for any repository with over 10,000 commits, so Solana's reference client had none. Commits are now also counted from the commits list for every repository, with one method, and Agave reads 4,303 commits on its default branch over the 51 full weeks to 2026-10-31, more than any other tracked repository.
- **Two operational risks need the owner, not code.** The nightly job runs about 125 minutes, so the private repository's free GitHub Actions allowance is likely to run out around 2026-11-19 unless the repository goes public or a spending limit is set; and the Dune reading is five days old and can only be replaced by hand.

## How it was checked

The same scans as the first pass, run again on the rebuilt warehouse at the 2026-11-05 pin: row counts, date ranges, gaps and null rates for every gold column; grain uniqueness from each table's declared grain; a spike scan on every numeric series; the `dq_*` tables; and a read of every model written since the first pass. Four things were measured rather than read:

- Every holdings row that had a price but no decimals was checked for decimals on its price row, and the lists' decimals were checked for consistency across all five reads (none varied).
- FastNear's transfer-time USD was compared with the day's closing price on the 6,091 NEAR transfers that have both.
- GitHub's `stats/commit_activity` for near/nearcore was compared with three other counts of the same year: the commits list, the search API and GraphQL's `history`, and one week's commits were swept across the repository's branches.
- DefiLlama's exchange-wallet series were read from silver for the nine exchanges that have history.

## Findings

### 1. Holdings could be valued at the pin, from the lists' own decimals

At the pin, `fct_wallet_holdings` read `no_decimals` on 5,261 of the 8,484 rows of the latest snapshot, and every one of those rows had a price from 1Click or Rhea, whose lists carry decimals. A list's price is per whole token counted with the list's own decimals, so the two belong together: a value computed with both is exactly what the list means. The first pass's sample had found the lists' decimals equal to the contract's on all 1,116 Rhea tokens and 132 1Click tokens that answered, and they never varied between reads.

**Fixed:** the lists' decimals stand in behind the registry and `ft_metadata`, marked `metadata_source = 'price_list'`. A contract that has answered is final, even with an error, so no list fills in behind it. The test `token_decimals_lists_match_contracts` fails if a list and a contract ever disagree; it has nothing to compare until the first night of `ft_metadata` reads, and from then on it is the guard. At the pin the latest snapshot now reads 970 rows valued ($641.3M), 3,158 with no price, 4,351 thin, 5 with the lists disagreeing, and none without decimals. `intents.near` sums to $233.8M against $248.2M of DefiLlama public TVL plus revenue.near.org's confidential TVL, a 5.8% gap, so `holdings_usd_latest_vs_tvl` no longer reads `not_available`. `omni.bridge.near` holds $191.6M, three quarters of it 106,619 ZEC, and `contract.main.burrow.near` $165.3M.

**Open:** 4,351 rows are `thin_price`, launch tokens with nothing behind their Rhea price, and that is right. The six tokens whose `balance_raw` is an empty string (51 rows across the snapshots) were already dropped by the balance filter and now also by the conversion; nothing changes for them.

### 2. The validator tables are a daily sample of epochs

`fct_validator_summary` holds 164 epochs between heights 4280 and 4938, a span of 659. The fetcher asks the archival node for the epoch in force at each day's first block, and the nightly read adds the current epoch, so the table holds one epoch a day out of about three, from 2026-04-19, the earliest epoch the node answers. The descriptions said "per epoch". A daily sample is fine for a stake-concentration series and wrong for anything counting epochs.

**Fixed:** the descriptions of `fct_validator_epoch` and `fct_validator_summary` say so, and SOURCES.md says where older history could come from (each staking pool's `get_total_staked_balance` at past heights, which the archival node does answer).

### 3. Exchange balances were in silver all along

The first audit listed exchange balances as not covered. DefiLlama's protocol list marks twelve protocols on NEAR as `CEX`, the wallets it labels on its exchange pages, and `fct_protocol_tvl_daily` rightly leaves them out of TVL, which is why nothing exposed them. Nine have history in silver, Binance's wallets from 2024-04-08 and Bitfinex's from 2022-11-14.

**Fixed:** `fct_exchange_balance_daily` holds them per exchange per day. On 2026-11-04: Binance $536.1M, KuCoin $21.7M, Bitget $18.9M, Gate $18.7M, Bitfinex $11.8M, Bitstamp $6.8M, SwissBorg $6.2M, Backpack $3.0M, Gate US $0.6M. The figure is every asset in the labelled wallets at DefiLlama's prices, so it is mostly NEAR and moves with NEAR's price; unlabelled wallets are missing, a relabelling moves the series, and DefiLlama can rewrite it. Flipster, MEXC and Bitlo are listed with no history because only the largest 25 protocols are fetched.

### 4. GitHub's weekly statistic is not the default branch, and Agave has none

`stats/commit_activity` answers HTTP 200 with a year of zeros, and `stats/contributors` with an empty list, for a repository with over 10,000 commits; anza-xyz/agave has 34,937. The first pass blanked such a repository. This pass counted the commits list instead and, to check the method, compared it with GitHub's statistic on near/nearcore, where both exist: 1,345 commits on `master` in the 51 full weeks to 2026-10-31 by the commits list, the search API and GraphQL's `history` alike, against 1,749 in the statistic. The difference is presumably commits on release branches; a sweep of one week found such commits on `2.14-release`. Across the 18 repositories the statistic runs both above and below the default branch, so it is not simply a broader count: MystenLabs/sui 5,067 against 2,823 on the default branch, aptos-core 2,419 against 1,659, avalanchego 1,273 against 935, go-ethereum 1,164 against 957, but ton-blockchain/ton 980 against 1,267 and near-api-js 250 against 383. For the small repositories the two agree exactly (aurora-engine 104, near/intents 179, near-sdk-rs 155, near-cli-rs 101, sputnik-dao-contract 6). A peer comparison drawn from the statistic alone would have overstated Sui's pace against NEAR's by nearly half.

**Fixed:** `github/commits_weekly` counts the default branch from the commits list for every repository, by committer date, with authors reduced to a count, and `fct_dev_activity_weekly` carries both measures: `commits` and `active_authors` are GitHub's statistic, empty for Agave; `commits_default_branch` and `authors_default_branch` are the one-method count, filled for every repository. Agave reads 4,303 commits over the 51 full weeks to 2026-10-31, more than any other tracked repository, with up to 35 authors in a week. The fetch costs about 250 calls a night with a token and reads only the zero-statistic repositories without one. `week_start` is now described as the Sunday that starts the week.

### 5. Native NEAR transfers have a USD value where FastNear gave none

FastNear values some transfers at transfer time and leaves the rest empty: 4,089 of 4,936 epoch-reward transfers to `treasury.near`, 201 native transfers and 57 attached deposits had no USD, so `fct_wallet_flows_daily.amount_usd` was empty on 67% of its rows and a USD series of the treasury's income could not be summed. The day's closing price is a fair stand-in: on the 6,091 NEAR transfers with both figures, the close-price value is within 1.9% of FastNear's on the median transfer, within 7.7% on nine in ten, and within 28% at worst, on days NEAR moved a fifth.

**Fixed:** `fct_wallet_transfers.amount_usd_estimated` takes FastNear's figure where there is one and the close-price figure for the other NEAR and wNEAR transfers, with `usd_basis` saying which; `fct_wallet_flows_daily` sums it. 4,134 transfers gained a value; 486 still have none, nearly all the 239 USDC fee receipts of September and October 2025 and a few bridged tokens. The test `wallet_usd_estimate_tracks_fastnear` fails if the median gap passes 5%, which would mean the price series and the transfers no longer line up. Epoch rewards to the treasury now read as about $0.5M a month in May to August 2026 and $1.36M in October.

### 6. Three in ten sampled transactions went to unlabelled receivers

In `fct_receiver_sample_daily`, 30.8% of sampled transactions since 2026-08-19 went to 7,498 accounts with no entity. The long tail cannot be labelled by hand, but the head could: `learn.sweat` alone took 1.8%, then `dex.intear.near`, `v2_1.omni.hot.tg`, `zcash-connector.bridge.near` and six more whose entity the name gives away.

**Fixed:** ten accounts added to `registry/entities.csv` with `name_only` evidence and `track_contract_stats`, so the nightly job also fetches their daily counts from NearBlocks. The labelled share of sampled transactions rises from 69.2% to 74.2%; 7,488 accounts, mostly tiny, remain unlabelled. Like the five batch-stream accounts added in the first pass, they stay unchecked in `dim_entity` until the 2026-11-06 run reads them.

### 7. Smaller findings

- `fct_yield_pools.apy_reward_pct` is empty on every row: DefiLlama reports no reward APY for any of the ten NEAR pools it lists, so the column is correct and empty.
- `fct_etf_nrr_daily` has no rows on weekends, which is right for a fund that prices on trading days; the fund page's NAV reaches the warehouse a day after its market price, so `dq_freshness` shows it two days behind.
- `fct_governance_proposals` keeps 15 proposals that never reached a vote, among them tests, duplicates and spam, as its description says; filter on status.
- `fct_contract_daily` holds only active days, so `vote.dao` ends on 2026-11-02 and `factory.bridge.near` on 2026-09-11, and a day inside a window with no row is a zero.
- The desktop app's side-session worktree sat untracked inside the repository at `.claude/worktrees`, where a `git add -A` would have embedded it; it is now ignored. Four worktree folders and five branches of the day's merged work remain beside the repository (`near-thesis-circulating-supply`, `near-thesis-holdings-usd`, `near-thesis-protocol-slugs`, `near-thesis-provisional-days`, and `worktree-ft-metadata` under `.claude`); all are merged into `main` and can be removed.
- Found in passing and left alone: `dq_reconciliation` has 35 rows with no subject, so its stated grain `check_id, subject` holds only because DuckDB treats two empty subjects as equal in `distinct`; the uniqueness test passes and the catalog is right, but a reader joining on the grain should know.

### 8. Operational risks

- **GitHub Actions minutes.** Each nightly run takes about 125 minutes (07:58 to 10:03 UTC on 2026-11-05) because the Intents Explorer tally walks 600 pages a night (59 minutes) and the receiver-sample backfill reads 20 days a night (41 minutes). About 540 minutes were used by 2026-11-05 against the 2,000 a month a private repository gets free, so the nine nights to the deadline add about 1,125 and the allowance is likely spent around 2026-11-19, after which the nightly job stops until December unless the repository is public, which makes Actions free, or a spending limit is set. The usage figure is on the owner's billing page, not visible from the API with this token. The Explorer backfill has 67 weekly days and about 600 in-between days still to walk, and the receiver backfill 287 days, so neither finishes before the deadline on its own; halving `BACKFILL_DAYS_PER_RUN` and `EXPLORER_PAGES_PER_RUN` would halve the cost at the price of slower history.
- **The Dune reading** is five days old and was taken by an AI-driven browser; `registry/sources.csv` asks for it to be replaced by hand.
- **Fifteen registry accounts are unchecked** in `dim_entity` until the 2026-11-06 run reads them, and the five batch-stream accounts have no daily counts yet, so `txns_ex_batch_streams` still cannot be built.

### 9. Still open from the first pass

| Item | State |
|---|---|
| Circulating supply | Done, from the lockup contracts; free float still unsized because the Foundation's liquid holding is not on chain under any known list |
| Token metadata fetcher | Written; first read on 2026-11-06. Holdings are valued now anyway (finding 1) |
| Provisional fee days | Done; re-measure the three-night window after a few more weeks of snapshots |
| Rebate removal on a receipt | Open; dated by archival config reads only |
| Agave's history | Done (finding 4) |
| USD for native transfers | Done (finding 5) |
| Treasury counterparties | Open; 30M NEAR of 2026 outflows still unlabelled |
| `txns_ex_batch_streams` | Waiting for the 2026-11-06 data |
| revenue.near.org's monthly series $1.72M above the wallets | Open |
| Terms to settle before going public | Open: CoinMetrics, DefiLlama, NearBlocks, Bitwise, Dune, 1Click, Rhea |

## Coverage, by thesis question

The playbook's metric framework names eight groups. Against them, at the 2026-11-05 pin:

| Group | Covered | With an independent check | Gap |
|---|---|---|---|
| A. Usage | Daily transactions, receipts, signers (v1), relayed accounts (v3), meta-transaction share and relayer count from 2025-10-28, new accounts, per-contract counts for 49 accounts, a 96-block-a-day receiver sample from 2026-08-19 with 70% of sampled transactions labelled | v1 against v3 transactions, 0.000% | No quality-adjusted index until the batch-stream accounts have data; the sample is 0.12% of blocks; no retention, cohorts or Top Level Account counts |
| B. Throughput | Blocks, chunks and shards per day from 2025-11-01, gas price | None | No per-shard TPS, block time or congestion level |
| C. Economic engine | Issuance, burn with the rebate rate in force, treasury share, Intents volume from three sources, fees, capture, revenue rebuilt from wallets, buybacks, the fee switch's channels, 1Click swaps by channel, pair, size and route | Wallets against DefiLlama, 0.3%; supply against the chain, 0.000% | Confidential Intents self-reported; DefiLlama's volume scope step on 2026-09-01; last two fee days provisional |
| D. Security | Validators, stake shares, Nakamoto coefficients and staking ratio daily from 2026-04-19; MPC participants and threshold on six reads; three liquid-staking tokens | Operators against the contract on every read | No validator history before April 2026; no TEE attestation; MPC cost (HSP-007 payouts) not followed |
| E. Capital | Chain TVL from 2021, 25 protocols' TVL, exchange wallets on NEAR, stablecoin total from 2021 and per asset at a point in time, yield pools, holdings in USD for 12 tracked contracts | Holdings against TVL within 15% on three protocols | Bridge flows; stablecoin history per asset; TVL history can be rewritten |
| F. Ecosystem | 18 repositories with two commit measures, 340 catalogue projects, governance proposals, veNEAR, four forum threads | Commit counts agree exactly on small repositories | A fixed repository list, not Electric Capital's taxonomy; no activity per catalogue project |
| G. Market | Price from three sources, market cap on a chain-built supply, fully diluted value, peers' fees, revenue, TVL, stablecoins and DEX volume, the Bitwise ETF's shares and NEAR | Prices within 0.12%; ETF shares chain against fund, exact | Peers' caps are project-reported; TON has no cap; no exchange flows or derivatives |
| H. Risks | Fee concentration by channel (swapkit 73%), volume by chain and asset, revenue mostly from one product, top holders per snapshot | NearBlocks against Dune public volume, 1.1% | Holder concentration over time; nothing social |

## What changed in this pass

| File | Change |
|---|---|
| `warehouse/models/gold/wallets/fct_wallet_holdings.sql` | Decimals and symbol from the price lists stand in behind the registry and `ft_metadata`; `metadata_source` gains `price_list` |
| `warehouse/tests/token_decimals_lists_match_contracts.sql` | A list's decimals must equal the contract's wherever both exist |
| `warehouse/models/gold/wallets/fct_wallet_transfers.sql`, `fct_wallet_flows_daily.sql` | `amount_usd_estimated` and `usd_basis`; the close price values NEAR and wNEAR transfers FastNear did not |
| `warehouse/tests/wallet_usd_estimate_tracks_fastnear.sql` | The close-price estimate stays within 5% of FastNear's figure on the median transfer |
| `warehouse/models/gold/capital/fct_exchange_balance_daily.sql` | New: DefiLlama's exchange wallets on NEAR per exchange per day |
| `ingest/sources/ecosystem.py` | `github/commits_weekly` counts the default branch from the commits list for every repository |
| `warehouse/models/silver/ecosystem/stg_github__weekly_commits_list.sql`, `stg_github__weekly_commits.sql` | The new count in silver; the statistic's model says what it is |
| `warehouse/models/gold/ecosystem/fct_dev_activity_weekly.sql` | `commits_default_branch` and `authors_default_branch` beside GitHub's statistic |
| `warehouse/models/gold/_gold.yml`, `warehouse/models/silver/_bronze.yml` | Descriptions for all of the above, the validator sampling, and `week_start` as Sunday |
| `registry/entities.csv` | Ten receivers from the block sample |
| `tools/catalog.py`, `README.md` | The exchange table in the catalogue groups and the table of contents |
| `tests/test_ingest.py` | The weekly bucketing of commits |
| `docs/SOURCES.md` | GitHub, exchange wallets, validator sampling, list decimals, and the holdings figures at the pin |
| `.gitignore` | The app's worktree folder |
| `data/bronze/github/commits_weekly/dt=2026-11-05/` | The commits-list counts for the 18 repositories, read on 2026-11-05 so the pin carries them |

Result: `make verify` passes 10/10 at the 2026-11-05 pin with 287 data tests (9 more than before: the two new singular tests, the list-decimals rows in the holdings unit test, and the generic tests on the new table and columns) and 95 unit tests; 64 gold tables and 608 documented columns (one table and 10 columns new); 70 reconciliation comparisons, 62 agreeing and 8 differing with explanations, none unavailable. No README figure moved. The bronze record grew by the 18 commit-count files, 1,930 files in all.

## What to do next

1. **Check the Actions allowance** on the billing page and decide: make the repository public once the terms in `registry/sources.csv` are settled, set a spending limit, or halve the two backfill batch sizes. Owner's decision.
2. **Confirm the 2026-11-06 nightly run** is green, that `rpc/ft_metadata` and `rpc/lockups` finished inside the night, and that the fifteen new registry accounts were read. Then move the pin.
3. **Build `txns_ex_batch_streams`** once the batch-stream accounts have a week of daily counts. Small.
4. **A fresh Dune reading by hand.** Owner's hands only.
5. **Validator history before April 2026** from each staking pool's `get_total_staked_balance` at monthly heights (about 400 pools at 70 dates, an hour and a half of archival calls). Medium.
6. **MPC cost**: the HSP-007 payouts to the 16 operators, from the paying account's transfers once it is identified. Research.
7. **Electric Capital's taxonomy** (the public `crypto-ecosystems` repository) as the repository list for NEAR and each peer, in place of the fixed list of 18. Medium.
8. **Treasury counterparties** and the revenue page's monthly series, both still unexplained. Research.
9. **Remove the merged worktrees and branches** beside the repository. Small, owner's call.
