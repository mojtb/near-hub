# The usage break of 2026-04-02

On 2026-04-02 `txns` fell 72% and `active_accounts_v3` fell 84%. Almost all of that came from two batch streams stopping within 17 hours of each other, and they made up most of what these columns counted. Activity outside them carried on at about the same level.

**What is known:** which accounts stopped, when, and how much of the fall they explain. **What is not known:** why. Neither Cosmose nor NEAR has made a statement that I could find.

## The evidence

Counts per account are NearBlocks' `/v3/accounts/{id}/stats/txns`, read on 2026-11-02. They are not in bronze, so `make verify` does not check them. Chain columns are `gold.fct_chain_daily`.

| Day | `txns` | Kai-Ching | Sweat migration | `txns` without them | `active_accounts_v3` | Kai-Ching accounts | Sweat accounts | v3 without them | `active_accounts_v1` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 03-21 | 3,114,793 | 2,272,351 | 0 | 842,442 | 2,323,338 | 1,998,402 | 0 | 324,936 | 135,621 |
| 03-31 | 4,169,826 | 2,268,809 | 940,541 | 960,476 | 3,282,359 | 1,996,758 | 940,520 | 345,081 | 139,225 |
| 04-01 | 3,758,663 | 1,371,003 | 1,434,827 | 952,833 | 2,956,760 | 1,195,760 | 1,434,823 | 326,177 | 139,048 |
| 04-02 | 1,063,375 | 2,175 | 144,241 | 916,959 | 466,287 | 18 | 132,306 | 333,963 | 137,183 |
| 04-03 | 907,861 | 0 | 0 | 907,861 | 341,016 | 0 | 0 | 341,016 | 131,893 |

Kai-Ching means transactions touching `hotwallet.kaiching` plus `users.kaiching`. Accounts means the distinct addresses `hotwallet.kaiching` or `sweat-migration.near` reached that day.

From 04-01 to 04-02, these streams explain 2,659,414 of the 2,695,288 lost transactions (98.7%), and all of the 2,490,473 lost v3 accounts. As daily averages, v3 without them was 341,110 for 1 to 22 March and 335,628 for 3 to 11 April.

## What stopped

**Kai-Ching's daily claim.** `hotwallet.kaiching` relayed a `claim` call to `earn.kaiching` for about 2,000,000 `*.users.kaiching` accounts a day. The monthly median of that daily count stayed between 1,999,995 and 2,000,001 from May 2025 to March 2026, with a standard deviation of 1,497 in March 2026. A count that constant is a fixed batch, so it does not measure how many people chose to use an app. `users.kaiching` also created about 118,000 accounts a day, 88% of `new_accounts` in 1 to 22 March. FastNear's index shows the main stream ending at about 14:18 UTC on 2026-04-01, and that day's count is 60% of a normal day.

**Sweat's key migration.** `sweat-migration.near` relayed `AddKey` actions to implicit accounts: 8,074,887 transactions from 03-23 to 04-02, with its last batch at about 07:16 UTC on 04-02. A further 222,984 ran on 04-28 and 04-29. Its main run lasted 11 days, so it inflated late March instead of lowering April.

HOT did not cause this. `0-relay.hot.tg` and `game.hot.tg` were flat across the date.

**Why the warehouse could not show this.** None of these accounts is in `registry/entities.csv`, so no contract in `fct_contract_daily` moved by more than about 27,000 a day. `fct_receiver_sample_daily` holds only 2026-10-31 at this pin. The accounts came from sampling 105 blocks from Neardata between 03-30 and 04-04, and the sample was used only to name them, because these streams arrive in bursts that a small sample misjudges.

**Why v1 barely moved.** v1 is distinct signers, and a relayed user is not a signer. NearBlocks documents neither count, so this comes from the numbers:

- v1 matches Nansen's published Q3 2026 distinct signers: minimum 42,517 on 09-16, maximum 106,771 on 07-06, and a mean of 79,289 against Nansen's "approximately 79,300". `txns` matches Nansen's 584,733 on 08-15 and 1,217,209 on 09-27.
- v3 is within 2% of v1 plus `meta_accounts` on all 369 days where all three exist.

## The cause, as far as it can be established

On-chain, the `*.kaiching` accounts were emptied after the stop:

- On 2026-05-08, five `*.kaiching` accounts sent 123,557.55 NEAR to `treasury.kaiching`.
- On 2026-05-12, `treasury.kaiching` sent 1,287,727.15 NEAR to `nfendowment03.near`, which had funded it with 76,000 NEAR in August 2023. The name suggests NEAR Foundation; that is not confirmed.
- From 2026-09-23 to 10-12, about 248,000 NEAR more left for one implicit account, `f370...bf7`.
- On 2026-11-02, `treasury.kaiching` held 0.1 NEAR, `hotwallet.kaiching` 1.78, `wallet.kaiching` 1.05 and `users.kaiching` 1.39.

Public sources:

- One [post by Vini B on 2026-05-08](https://www.kucoin.com/news/insight/NEAR/69fe6209d064730007b45488), republished by KuCoin, reports these transfers "amid discussions" of the project having ceased operations. It says this is not confirmed and asks Cosmose and NEAR for clarity. Its transfer amounts match the chain.
- [TechCrunch in 2023](https://techcrunch.com/2023/04/24/near-cosmose-ai/) ties Kai-Ching to Cosmose's KaiKai app. The link from these accounts to Cosmose rests on the name and that reporting.
- NEAR's Q2 2026 figures, seen only in a [copy of a Tron Weekly article](https://pro.edgex.exchange/es-LA/news/article/near-protocol-q2-2026-update), give 854,000 transactions and 121,000 addresses a day, matching this warehouse, with no comparison to Q1. [Nansen's Q3 2026 report](https://www.nansen.ai/post/near-q3-2026-report) has no April data.
- I found no announcement of `sweat-migration.near`. [Sweat's notices](https://update.swe.at/) do not mention it. Its 04-29 batch fell on the day of the [SWEAT exploit](https://www.theblock.co/news/regulation/2026-04-29-sweat-protocol-thwarts-multi-million-dollar-exploit-restores-user-balances-399498), and I did not establish a link.

## What this means for usage claims

| Column | Across 2026-04-02 | Use it this way |
|---|---|---|
| `txns`, `receipts` | Not comparable | Before April, subtract Kai-Ching and the Sweat migration, or start after 04-03 |
| `active_accounts_v3`, `meta_accounts`, `meta_txns`, `meta_txn_share` | Not comparable | Same |
| `active_contracts_v1`, `active_contracts_v3`, `new_accounts` | Not comparable | Same. `active_contracts` fell from about 2.2M to about 190,000 |
| `active_accounts_v1` | Comparable | Distinct signers only, so it misses relayed users. It has breaks of its own: it ran from 251,386 to 592,250 on 02-03 to 02-18, against about 145,000 in March |
| `gas_fee_near` | A real change | Fell from 2,737 to 777 NEAR a day (1 to 22 March against 3 to 11 April). This is gas actually paid, not a definition problem, so any burn claim needs it. A 48-block sample puts `*.kaiching` at 57% to 75% of gas burned before the stop, and that sample is rough because the stream arrives in bursts |

Three things not to conclude:

- **"Usage collapsed across the chain in one day."** It did not. One program's fixed batch and a temporary migration stopped, and everything else carried on.
- **"So usage is fine."** It is not. Without the streams, from 1 to 22 March to October 2026, `txns` fell from about 1,012,000 to 712,000 a day (down 30%), v3 from 341,110 to 131,814 (down 61%), and v1 from 145,327 to 72,046 (down 50%).
- **"Kai-Ching's accounts were fake."** The data shows a fixed daily batch, signed by one account. It says nothing about whether people stood behind those accounts, and the post above argues that they did.

The problem reaches further back than April. The fixed batch is visible as far back as NearBlocks' per-account window goes, to April 2025, and `hotwallet.kaiching` first signed on 2023-08-09. FastNear counts 1.32 billion transactions touching it, 24% of the 5.47 billion in `fct_chain_daily`.

Two related breaks:

- **2026-04-13 to 04-14:** `relay.tg` fell from 118,799 to 930 transactions a day and `0-relay.hot.tg` halved. This is why the v3/v1 ratio went from about 2.5x to the 1.9x seen since. I did not look into why.
- **2026-12-30, scheduled:** Sweat Wallet [ends in its present form](https://update.swe.at/). `sweat-relayer.near` alone was 26% of October's transactions, so another break is likely.

## Re-run it

All of these worked without a key on 2026-11-02.

```bash
curl -s "https://api.nearblocks.io/v3/accounts/hotwallet.kaiching/stats/txns?limit=365"
```

```bash
curl -s "https://api.nearblocks.io/v3/accounts/users.kaiching/stats/txns?limit=365"
```

```bash
curl -s "https://api.nearblocks.io/v3/accounts/sweat-migration.near/stats/txns?limit=365"
```

```bash
curl -s -X POST https://tx.main.fastnear.com/v0/account -H 'Content-Type: application/json' -d '{"account_id":"hotwallet.kaiching","limit":1,"desc":true,"is_signer":true,"to_tx_block_height":192152031}'
```

```bash
curl -s -X POST https://transfers.main.fastnear.com/v0/transfers -H 'Content-Type: application/json' -d '{"account_id":"treasury.kaiching","limit":100,"desc":true}'
```

The NearBlocks window is 365 days of activity, and `date=` is ignored on this endpoint. The April 2026 rows can therefore fall out of it, which is a reason to capture them in bronze.
