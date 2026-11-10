# Circulating supply

`circulating_supply_near` is now built from the chain, in `fct_circulating_supply_daily`. On 2026-11-04 it reads **1,308.69M NEAR, 99.84% of the 1,310.83M total supply**. `market_cap_usd` in `fct_market_daily` is price times that figure: **$5.26B** that day, against a fully diluted $5.27B.

The audit of 2026-11-05 (finding 2) found that nothing in the warehouse carried a live figure. This page says how the new series is built, how it was tested, why the old figures went wrong, and what it leaves out. The largest thing it leaves out is a question of basis: NEAR's figure counts the NEAR Foundation's liquid tokens as circulating, and some peers' figures clearly leave out far more. See [Against peers](#against-peers).

## What it measures

[NEAR's post on token supply](https://near.org/blog/near-token-supply-and-distribution) defines circulating supply as every token not subject to a lockup at that moment. Staked tokens count, because staking is not what the definition tests. Tokens the Foundation holds outside a lockup count too.

The formula is the one [NEAR Explorer used](https://github.com/near/near-indexer-for-explorer/blob/master/circulating-supply/src/main.rs) until that project stopped in 2023, and NearBlocks copied it:

```
circulating supply = total supply
                   - what every lockup contract still locks
                   - the balances of lockup.near and contributors.near
```

`lockup.near` funds new lockups. `contributors.near` held 418M NEAR at genesis and holds under 5 now. Together they hold 0.17M.

## How it is built

| Step | What happens | Result at the pin |
|---|---|---|
| List the lockups | Every lockup is a subaccount of `lockup.near`, so that account's transfers on FastNear list them. Each funding is one lockup, because a name comes from its owner and 15 owners were given a second lockup after deleting the first | 5,379 lockups under 5,364 names, 876.37M NEAR funded. None date from genesis, which held 581.8M in `foundation.near` and 418M in `contributors.near` |
| Read each schedule | `view_state` at a block just after creation gives the amount and the lockup, release and vesting terms. `view_account` gives the code version | All read |
| Follow what changed | Read each contract again at the tip, or just before its last transfer if it is gone. A block search dates when any termination started and finished | 180 vesting terminations from 2020-10-03 to 2026-06-02, 11.2M NEAR withdrawn, 14 still open; 3,424 lockups deleted; 1 replaced by another contract |
| Sum per day | Gold evaluates the formula for every lockup at each day's close, from 2020-10-13, when transfers were enabled | 2,214 days |

Three rules come from the contracts, and NEAR Explorer applied the same ones:

- An early contract version measures its release from the day transfers were enabled, and not from the end of the lockup, so it ends sooner. 4,944 lockups run one of the two versions Explorer named.
- During a termination the contract locks the unvested amount, whatever the schedule says, until the Foundation has withdrawn it. The median termination took 21 days to finish and the longest 745. Getting this stage wrong moved the series by up to 1.9M NEAR for weeks at a time, which is how the fit to NearBlocks exposed it.
- A contract whose owner never called `check_transfers_vote` still answers that its whole amount is locked, although that only waits on the owner. The formula treats those tokens as released on schedule. They are reported in `transfers_never_enabled_near`: 19.35M NEAR in 221 lockups today. A stricter reading subtracts them and gets 1,289.34M, 98.36% of total. None of it has ever left those contracts.

Owners are people's accounts, so bronze holds no account names. A lockup is known by its number in the factory's order, and its owner and staking pool are dropped, in keeping with how the Intents Explorer data and the ETF pool's other delegators are handled.

## How it was tested

| Test | Independent of the formula? | Result |
|---|---|---|
| NearBlocks' figure, from its own lockup job and its own list of lockups, through 2025-08-26. How it filled in the years before that job began in January 2024 is not documented | Yes | 0.006% apart on the last day (1,249.72M against 1,249.65M). Over the 1,640 days outside its failure window (below): median gap 0.0001%, under 0.1% on 1,608 days, largest 0.37% on 2025-03-13. In 2022 the yearly means are equal to the last digit shown, 729.096M |
| The contracts' own `get_locked_amount` at eight past days and at the tip | Same contracts, different code | 832 answers, 507 of them with something locked, 91.1M NEAR in all. Every one matches to within 0.001 NEAR. That includes the 248 whose owners had not turned transfers on, which answer their whole amount, as expected |
| NEAR's published schedule, last updated 2020-10-16 | Yes, a plan made five years earlier | Within 3.3% at every yearly milestone after launch (table below) |
| When genesis allocations finished unlocking | Yes | The plan says month 60, which is 2025-10-13. On 2025-10-14 the lockups made in 2020 hold 91 NEAR together; the 7.6M NEAR still locked that day is in lockups made later |
| Bitwise's prospectus: market cap of $3.1B on 2026-06-15 | Yes, but rounded | Ours is $3.09B. The rounding cannot tell circulating from fully diluted |
| Total supply | Yes | NearBlocks' total is held to the archival node by an existing data test |
| `lockup.near` and `contributors.near` balances | Yes | FastNear's running balance equals `view_account`, at the tip and at past heights |

The fetcher's read path was also run fresh on 19 lockups across every case (terminated, deleted, dormant, still running, replaced), and each row came out identical to the stored one, down to the dated terminations.

| Milestone | Date | Chain | NearBlocks | Published plan | Plan's total supply | Actual total supply |
|---|---|---:|---:|---:|---:|---:|
| Launch | 2020-10-13 | 235.06M | 235.10M | 156.5M | 1,000.0M | 1,000.00M |
| Start of Year 2 | 2021-10-13 | 519.45M | 519.45M | 507.8M | 1,051.2M | 1,049.31M |
| Start of Year 3 | 2022-10-13 | 811.14M | 811.14M | 838.2M | 1,104.9M | 1,102.22M |
| Start of Year 4 | 2023-10-13 | 984.69M | 984.69M | 1,012.1M | 1,161.5M | 1,158.19M |
| Start of Year 5 | 2024-10-13 | 1,142.36M | failing | 1,163.7M | 1,220.9M | 1,215.07M |
| Start of Year 6 | 2025-10-13 | 1,267.69M | frozen | 1,283.4M | 1,283.4M | 1,275.90M |

Launch differs on purpose: NEAR's post warned that unclaimed tokens, over 300M at the time, sat in unlocked accounts until claimed. After that the chain runs below the plan, mostly because lockups kept being made after launch (175M NEAR from 2021 on) and total supply came in lower than planned.

Nothing but the contracts themselves has tested the series since 2025-08-26, because every other source now reports total supply or a frozen number. It moves little: only 1.97M NEAR is still locked, in 37 lockups, and every schedule is public.

## Why the old figures went wrong

**NearBlocks.** Its job read every lockup, which is why its history is such a good test. Then three things happened:

1. From 2024-08-12 to 2024-12-28 the job misbehaved. A lockup it failed to read three times [counted as nothing locked](https://github.com/Nearblocks/nearblocks/commit/87f4b8b372), so RPC failures pushed its figure as high as 99.95% of total. From 2024-11-04 such a failure stopped the job instead, and its figure stood still until 12-28.
2. Its [rewrite of 2025-09-03](https://github.com/Nearblocks/nearblocks/commit/f70a80f58e) removed the job, so `/v1/charts` and `/v1/stats` have read 1,249,836,992 since 2025-08-27.
3. On [2025-10-23](https://github.com/Nearblocks/nearblocks/commit/ccff1f23f3) it pointed `/v1/legacy/circulating-supply` at total supply, and its new stats job does the same, with a comment saying all genesis-locked tokens were released by October 2025. That is true of genesis tokens and ignores the later lockups, a difference of 0.16% today.

**CoinMetrics.** [`CapMrktEstUSD`](https://docs.coinmetrics.io/network-data/network-data-overview/market/market-capitalization) uses a supply reported by the project and collected through CoinGecko. For NEAR that report is almost certainly NearBlocks' endpoint, which answers `format=coingecko`. The data shows it: a median gap of 0.015% from November 2024, two months carrying NearBlocks' frozen figure, and a jump on 2025-10-25, two days after that commit, to the previous day's total supply, which it has followed since. So the check the audit added compared one number with itself. It is now marked `same_upstream`.

**So was market cap really fully diluted?** Yes, since 2025-10-25, but that is now a small error. Fully diluted ran 1.4% above circulating in August 2025, 0.6% in October 2025 and 0.16% today. CoinMetrics' older values were less reliable: its cap ran 8% below ours on 2021-10-13, and its median day since mid-2021 differs by 0.23%.

| Day | Total supply | Chain | NearBlocks | CoinMetrics implied |
|---|---:|---:|---:|---:|
| 2024-06-30 | 1,198.13M | 1,093.38M | 1,093.38M | 1,092.96M |
| 2024-10-13 | 1,215.07M | 1,142.36M | 1,214.52M (failing) | 1,214.25M |
| 2025-06-30 | 1,258.06M | 1,230.28M | 1,230.16M | 1,229.97M |
| 2025-08-26 | 1,267.70M | 1,249.72M | 1,249.65M | 1,249.40M |
| 2025-12-31 | 1,283.94M | 1,278.77M | 1,249.84M (frozen) | 1,283.86M |
| 2026-11-04 | 1,310.83M | 1,308.69M | 1,249.84M (frozen) | 1,310.75M |

## Against peers

`fct_peer_daily.market_cap_usd` is not on one definition, so the table now says what each row rests on, in `market_cap_basis` and `implied_supply_tokens`. Peers use the CoinMetrics estimate, which is whatever each project reports. NEAR uses the series above. Here is the supply behind each cap on 2026-11-04, against total supply read from each chain on 2026-11-05:

| Chain | Supply behind the cap | Total supply | Share | Total read from |
|---|---:|---:|---:|---|
| Sui | 4,139M | 10,000M | 41% | Sui GraphQL `coinMetadata` |
| Aptos | 884M | 1,211M | 73% | Aptos `0x1::coin::supply` |
| Solana | 590M | 637M | 93% | Solana `getSupply`, whose own circulating figure is 590.32M |
| Avalanche | 444M | 476M | 93% | Avalanche `platform.getCurrentSupply` |
| NEAR | 1,309M | 1,311M | 99.8% | Block header |
| Ethereum | 122M | 122M | 100% | CoinMetrics `SplyCur`, which it indexes from the chain itself |
| TON | not read: the asset id asked for, `ton`, returns nothing; CoinMetrics lists Toncoin as `gram` | | | |

NEAR's 99.8% is not free float, and it is not the same measure as Sui's 41%. NEAR's definition takes out only lockups, while the NEAR Foundation also holds liquid NEAR: [305M on 2024-01-11](https://www.theblock.co/news/business/2024-01-11-near-foundation-staff-cut-treasury-271858), about 26% of supply then, which is the last figure found. No list of its accounts is published, so that holding cannot be read from the chain. `treasury.near` holds a further 1.6M.

So a chart of NEAR against Sui, or any peer whose report leaves out reserves, compares different things. To put NEAR on a narrower basis, take the Foundation's holding off the supply, and say that the number is old. These readings are in `registry/near_supply_readings.csv`.

## What it does not do

- It does not start before 2020-10-13. No token could move before then.
- It is not a free float, for the reasons above, and it does not take out long-dormant wallets or exchange balances.
- A deleted lockup counts as holding nothing after its last transfer. On seven of them the formula still shows something locked just before that moment, 27,285 NEAR in all, so the formula and the contract differ slightly there.
- Some small gaps to NearBlocks stay unexplained, such as 0.84M from 2021-06-11 to 2021-07-05, and 0.12M on many days of 2025. Single-day gaps of up to 4.4M in 2025 are NearBlocks' own: its figure dips for one day and returns.

## Keeping it current

The nightly job runs `rpc/lockups`. It reads the factory's list again, reads any new lockup, and looks at the few contracts that can still change: schedules still running, open terminations, and lockups with transfers never turned on. It saves a row only when something changed, and it reads the contracts' own answers for the running lockups, so the formula is tested again each night. A new contract version would fail `lockup_formula_matches_contract` rather than pass unnoticed.

The history in bronze was read on 2026-11-05. A first read from nothing takes up to five calls per lockup at the archival host's pace of 1.5 seconds, which is many hours, so it runs in batches of 200 lockups a run.
