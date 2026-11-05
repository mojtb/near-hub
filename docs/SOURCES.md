# Data sources

The table of sources, limits and terms lives in [`registry/sources.csv`](../registry/sources.csv), so it can be queried like everything else. This page records what that table cannot: how each source behaves, what is known to be wrong with it, and what was tried and rejected.

Sources were last tested on 2026-11-01. Each nightly run records what it fetched in `data/bronze/_manifest/` and how each dataset went in `data/bronze/_runs/`.

## How independent are the sources?

This matters more than how many sources agree.

| Family | Sources | Upstream |
|---|---|---|
| NEAR's own uploads | revenue.near.org, the Dune Intents dashboard, DefiLlama's Intents fees and revenue | NEAR uploads datasets to Dune. DefiLlama's adapter reads them, and its source says it mirrors revenue.near.org. Their close agreement proves little. |
| The chain, read directly | RPC, archival RPC, Neardata | Independent |
| The chain, indexed by others | NearBlocks, FastNear | Independent of NEAR's uploads, but each is one company's indexer. Public Intents only. |
| Markets | CoinMetrics, Coinbase, DefiLlama prices | Independent of the chain |
| The Bitwise NEAR ETF's own numbers | Bitwise's page, SoSoValue's reported flows | SoSoValue's flows work out to Bitwise's share changes times NAV, so they are not a second opinion. The chain is. |

Confidential Intents appear only in the NEAR family. Nothing here checks them independently, so treat them as self-reported.

The strongest checks are the ones that cross families. See [RECONCILIATION.md](RECONCILIATION.md), where `independence` marks each comparison.

## Notes per source

### NearBlocks
- v3 daily endpoints return at most 365 days per call. `limit` counts days, not rows, and `date=` returns a single day. History therefore grows with each stored snapshot.
- Legacy `/v1/charts` is the only full daily history back to 2020-07-21, and `/v1` is marked for eventual removal. The bronze copy protects against that.
- v3 `stats.circulating_supply` equals total supply, which is wrong. Circulating supply comes from `/v1` instead.
- `/v1` circulating supply is stale too: it has read 1,249,836,992 NEAR on every day since 2025-08-27, on `/v1/charts` and `/v1/stats` alike. Gold keeps the column, the catalog marks it, and `circulating_supply_latest_nearblocks_vs_coinmetrics` in [RECONCILIATION.md](RECONCILIATION.md) shows the gap. No source in this warehouse has a live circulating figure.
- v1 and v3 `active_accounts` are undocumented, and the gap between them is not stable: about 1.8x over the latest 30 days, but 9x to 18x in monthly averages from October 2025 to March 2026. The numbers show what each counts. v1 matches Nansen's published distinct signers, and v3 stays within 2% of v1 plus `meta_accounts`, so it also counts users whose transactions a relayer signs. Gold keeps both and calls neither "daily active users". `txns` and v3 cannot be compared across 2026-04-02: see [USAGE_BREAK_2026-04-02.md](USAGE_BREAK_2026-04-02.md).
- Prices are stamped at 00:00 UTC, which makes the value on day D the close of day D-1. Gold moves them back one day, after which they match the other price sources within about 0.1%.
- `tvl-stats` is a different measure from DefiLlama's chain TVL, about a third of it.
- All 16 MPC operators show `tee.status = none` at NearBlocks, while NEAR says Chain Signatures run inside TEEs. A blank here may only mean NearBlocks has no attestation data. Check the contract before claiming anything.

### DefiLlama
- Intents fees and revenue come from NEAR's Dune datasets, not an independent count. Read the [adapter](https://github.com/DefiLlama/dimension-adapters/blob/master/fees/near-intents/index.ts) before citing them.
- Revenue means NEAR and wNEAR swept into three wallets, excluding hops between them. Sweeps are periodic, so a single day's revenue can exceed that day's fees.
- Its Intents volume changes meaning on 2026-09-01. From 2026-04-01 to 2026-08-31 it matches NearBlocks' public-only figure within 0.2%, and from 2026-09-01 it equals revenue.near.org's all-routes figure, which includes confidential Intents. The adapter has no date rule, so DefiLlama probably kept its stored values when NEAR restated the earlier months; that is not confirmed. Two checks in [RECONCILIATION.md](RECONCILIATION.md) hold this. Read a volume trend across that date from revenue.near.org or NearBlocks, never from DefiLlama.
- `bridges.llama.fi` returns HTTP 402 and is not used.
- `/protocols` and `/protocol/<slug>` are large, so they are trimmed to NEAR before saving, and the manifest note records that. `/protocols` also lists exchange wallets on NEAR, which gold marks with `is_cex` and leaves out of TVL.

### revenue.near.org
- Rendered tiles show 0 in plain HTML, but the real series are embedded in the Next.js payload. `ingest/parsers/revenue_page.py` reads them and fails loudly if a series disappears.
- `protocol_fee_near`, `intents_revenue_near` and `burn_revenue_near` are 0 on every row. Only total fees carry information.
- Three cumulative revenue figures appear on or around this page, and they do not match. See `intents_revenue_all_time_defillama_vs_page_monthly` in [RECONCILIATION.md](RECONCILIATION.md).

### FastNear
- Transfers carry a USD value at transfer time, which is FastNear's own calculation.
- The crawl walks oldest to newest with `resume_token` and resumes where it stopped.
- `intents.near` and token contracts have far too many transfers to crawl, so they use daily contract statistics instead.
- A fee collector can have no native account at all: `7066...f05` holds balances only inside `intents.near`, so `view_account` reports it as unknown. That is expected.

### CoinMetrics
- `CapMrktEstUSD` divided by `PriceUSD` tracked NearBlocks' circulating figure until September 2025 and has equalled total supply since November 2025, so `market_cap_usd` in gold is a fully diluted cap from then on. The community data does not say why the estimate changed.

### Archival RPC
- `block`, `view_account` and `call_function` work at old heights.
- `validators` by `epoch_id` worked for an epoch in May 2026 and returned `UNKNOWN_EPOCH` for one in October 2024, so validator history is partial.
- Calls hit HTTP 429 quickly. The free RPC host recognises a FastNear key, but the archival host shows no sign of it, so archival calls keep the keyless pace.

### Token metadata (`rpc/ft_metadata`)
- Asks each token seen with a positive balance in `fastnear/account_full`, or seen in `fastnear/ft_top_holders`, what its contract says through `ft_metadata`. 7,933 tokens had been seen by 2026-11-05, nearly all held by `dclv2.ref-labs.near`, `v2.ref-finance.near` and `intents.near`.
- Each token is read once. Answers are kept in `data/state/rpc__ft_metadata.json`, and each run's new answers in one bronze file. An answer whose bronze file has gone is read again, because the nightly job drops its own bronze dated up to `main`'s pin, so a run on the pin's day would otherwise lose those tokens for good.
- A night makes at most 2,000 calls, tokens with the most rows first, so the backlog takes four nights and later nights ask only about new tokens. At the keyed pace of 0.15 s a call that is about 5 minutes, but this pace has only been seen on runs of about 50 calls, so check the first night's time in `data/bronze/_runs/`.
- Without a key, one call a second drew HTTP 429 after about 3 minutes, and 300 tokens took 412 seconds. A run stops after 40 minutes, which limits a keyless run to about 1,750 tokens and keeps a node that rate-limits every call from stretching the night past the job's timeout.
- `icon` and `reference` are dropped, because an icon can be a large image. `spec`, `name` and `symbol` are cut to printable characters and to 32, 128 and 64 characters, because a contract can put anything there.
- Some answers are final and are kept: `UNKNOWN_ACCOUNT` (the contract is gone), `INVALID_ACCOUNT`, `NO_CONTRACT_CODE`, `CONTRACT_EXECUTION_ERROR` (no such method, or it panicked), `NOT_METADATA` (it returned something else) and `BAD_DECIMALS` (not a whole number from 0 to 255). These tokens stay empty in gold.
- Any other error says something about the node, not the token, so the token is asked again on a later run, after the tokens that have not failed yet. Three failures in a row, or one call that used up its retries, end the run for that night.
- Name and symbol are the contract's own claim: `usdc-4d51ec.launchpad.justhoot.near` calls itself USDC, with 18 decimals. `fct_wallet_holdings.metadata_source` shows which rows rest on a claim. Group by `token_id`, and treat these fields as untrusted text when displaying them.
- A sample on 2026-11-05, not stored: of 300 tokens picked at random, 296 gave decimals, 2 no longer exist and 2 are `mock-ft` contracts that panic. So about 99% of holdings rows should convert once the backlog is read. All 12 registry tokens' decimals matched their contracts, and so did all 30 tokens read that 1Click lists. `token_decimals_match_ft_metadata` holds the registry to the contracts from now on.

### Token prices (`fct_token_prices`)
- Two lists price NEAR tokens: 1Click's `/v0/tokens` and Rhea's `list-token-price`. On 2026-11-05 they were read about four minutes apart. A holding uses the prices read in its own snapshot and no others, so all 382 rows of 2026-10-28, before either list was fetched, have no value.
- Prices join on token id, never on symbol. `usdc-4d51ec.launchpad.justhoot.near` calls itself USDC, is held by `dclv2.ref-labs.near`, and is on neither list, so it has no price at all.
- For 1Click the token id is the NEAR contract named in `assetId`, not `contractAddress`. Filtering on `blockchain = 'near'` finds 39 tokens. USDC on Ethereum is listed under `eth` with a 0x address, yet its asset id names `eth-0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48.omft.near`, which is the contract `intents.near` holds. The asset id finds 152 tokens, 142 of them held, against 33 held on that filter. On the sample below it adds $97.8M, 42% of what `intents.near` holds. Three tokens are listed twice, with the same price and decimals.
- 1Click wins where it has a positive price, because 139 of its 152 tokens carry a market feed's id (`coingeckoId`), while Rhea's list is one DEX's pools. A price of 0 means no price: 1Click lists six tokens at 0, and Rhea prices three of them.
- Native NEAR takes `wrap.near`'s price, because one redeems for the other one to one.

**When the lists disagree.** 26 tokens are on both lists at every read, which makes 130 comparisons. The gap is a percent of the larger price. It grows as Rhea's pools get thinner:

| Vetted assets opposite the token on Rhea | Comparisons | Median gap | Largest gap | Over 20% |
|---|---:|---:|---:|---:|
| Under $1,000 | 15 | 0.38% | 32.1% | 5 |
| $1,000 to $10,000 | 21 | 0.64% | 28.2% | 2 |
| $10,000 to $100,000 | 54 | 0.50% | 10.7% | 0 |
| $100,000 or more | 40 | 0.24% | 4.1% | 0 |

- Above 20% (`price_disagreement_pct` in `dbt_project.yml`), `value_status` reads `sources_disagree` and the value stays empty. Nothing here says which list is right, and the next largest gap is 10.7%, so the line is not close to anything normal.
- Two tokens are over it. `lsd-usdt.rhealab.near` is on Rhea at 1.46973 at every read, against about 1 on 1Click, with about $1 opposite it. HAPI fell from 0.181 to 0.141 on 1Click on 2026-11-04, while its Rhea pool, with about $1,800 opposite, stayed near 0.20. Both are worth little here: about $2,300 of HAPI at 1Click's price and under $10 of the other.
- `token_prices_agree_where_rhea_is_deep` fails if a gap over 20% appears with $100,000 or more behind Rhea's price, because then a real position goes blank and someone should look. `token_prices_latest_rhea_vs_oneclick` in [RECONCILIATION.md](RECONCILIATION.md) holds the median ratio to 2%. It has read 0.9999 to 1.0046.
- `lst_price_latest_lists_vs_contract` compares LiNEAR, rNEAR and stNEAR with their contracts' own rates times `wrap.near`'s price. Over the 15 comparisons so far the largest gap is 1.06%. That matters because LiNEAR and rNEAR are priced by Rhea alone and hold about $107M at `contract.main.burrow.near`.

**Stale and thin Rhea prices.**
- Most of Rhea's list does not update. 4,309 of the 4,609 tokens on all five reads kept one exact price while NEAR moved 11%, and a price set against wNEAR should have moved with it. Rhea gives no time, so `price_date` is the first read showing that exact price. Filter on `price_date = snapshot_date` to keep only prices that changed since the last read.
- A listed price says nothing about size. `lambo.meierbach.near` lists at $512 on the strength of 1 wNEAR, about $4, opposite it, and `v2.ref-finance.near` holds 90.9M of it, which would read $46.5B. `inear.tkn.near` would read $683M with $487 opposite. Launch tokens are the quiet version: `dclv2.ref-labs.near` holds up to a billion each of thousands of them, typically worth about $0.000005 on Rhea's list, which would add about $20M with almost nothing opposite.
- A strange number alone is not the problem. The 8.9e17 `neardog.tkn.near` at `v2.ref-finance.near` come to $256 at Rhea's $2.88e-16, with $190 opposite. `shmrt-1315.meme-cooking.near` lists at $1.36 trillion, the highest price on the list, but its pool holds 9.3e-10 of a token, so that row reads $1,263 with $1,061 opposite. Both rows get a value.
- Rhea's own `tvl` field has the same flaw, because it prices each side at its listed price. Pool 5746 holds only ELON and INEAR, and reads $1.367B of the $1.388B total across all 3,159 pools. So depth is measured another way.
- `depth_usd` sums the assets with a vetted price (1Click's, or a registry token at Rhea's) opposite the token, across Rhea's pools. It is real money: faking it means depositing it. In a constant-product pool, selling any amount of a token cannot take out more than the other side. Concentrated-liquidity (DCL) pools are not in Rhea's pool list, so a token traded only there reads 0.
- A token that is not vetted gets a value only up to 3 times its depth (`price_depth_multiple`). Above that, `value_status` reads `thin_price`: `price_usd` stays visible and `value_usd` stays empty, so `sum(value_usd)` is safe. A pool's own reserves read about 1, as a constant-product pool should. Among the 167 such tokens at `v2.ref-finance.near` with over $1,000 of depth, the median is 1.01 at a price that changed since the last read and 1.18 at one that did not, and 90% are under 1.4.
- The multiple hardly matters. On the sample below, 2, 3, 10 and 1,000 times depth value these tokens at $2.25M, $2.33M, $2.44M and $3.17M, out of $641M in all. With no limit they would read $47.2B.
- Tokens in `registry/tokens.csv` are exempt, because each was listed by hand with evidence. LiNEAR's $45M at Burrow is 32 times its depth and is real, since a lending market holds far more than any pool could absorb. `xtoken.rhealab.near` has $133 opposite it and $3.9M at Burrow, so it rests on Rhea's price alone. That price is RHEA's times the contract's `get_virtual_price`, 1.11747 when read by hand on 2026-11-05, so it does not come from the thin pool.

**Decimals.** A price is per whole token, counted with the list's own decimals. If the holding's decimals differ, the value would be off by powers of ten, so `value_status` reads `decimals_disagree`. No row reads this today: on the sample below, Rhea's decimals matched the contract on all 1,116 tokens that answered, and 1Click's on all 132. The rule stays as a guard, tested on made-up rows.

**How much gets a value.** A sample on 2026-11-05, not stored, read all 932 held tokens that could get a value, plus about 400 others, and 12 of the 1,330 gave no decimals. So the sample column is close to what the full backlog gives, except that the rows it did not read move from `no_decimals` to `thin_price`, because they have nothing opposite them.

| `value_status`, latest snapshot | At the pin | With the sample | After the backlog, estimated |
|---|---:|---:|---:|
| `valued` | 65 (0.8%) | 968 (11.4%) | 968 (11.4%) |
| `no_price` | 3,158 | 3,158 | 3,158 (37.2%) |
| `no_decimals` | 5,261 | 3,758 | about 45 |
| `thin_price` | 0 | 595 | about 4,300 (51%) |
| `sources_disagree` | 0 | 5 | 5 |
| Sum of `value_usd` | $340.7M | $641.3M | $641.3M |

Few rows get a value because most rows are launch tokens that nothing else trades against. The money is elsewhere: of the $641.3M, 1Click prices $522.7M (226 rows), Rhea prices $116.3M on registry tokens (22 rows), and Rhea prices $2.3M on all other tokens (720 rows). Across all snapshots the sample values 4,833 of 42,556 rows.

**Checked against other sources.** `holdings_usd_latest_vs_tvl` sets the sums against TVL from outside the chain read. The Intents row stays `not_available` until bridged assets have decimals, because without them `intents.near` sums to only $86.1M.

| Contracts | Sum of `value_usd` at the pin | With the sample | Compared with | Gap with the sample |
|---|---:|---:|---|---:|
| `contract.main.burrow.near` | $158.5M | $165.3M | DefiLlama `rhea-lend`, $153.5M | 7.1% |
| `v2.ref-finance.near`, `dclv2.ref-labs.near` | $23.2M | $28.3M | DefiLlama `rhea-dex`, $24.1M | 14.9% |
| `intents.near` | not available | $233.8M | DefiLlama `near-intents` plus revenue.near.org's confidential TVL, $248.2M | 5.8% |

The Rhea DEX gap read 27% on 2026-11-01 and 24% on 11-02, so its tolerance is 30%. About 97,000 QTC, $6.9M, left `dclv2.ref-labs.near` on 11-03, and DefiLlama's figure did not move with it, so it appears not to count QTC.

### Neardata
- A block is about 265 KB, so raw blocks are counted and thrown away.
- The published limit is 180 requests per minute, but three parallel workers hit HTTP 429 from this machine. The sampler runs one request at a time.
- Sample results are estimates. `fct_receiver_sample_daily` keeps `blocks_sampled` on every row.

### Intents Explorer API
- Covers 1Click swaps only, despite being the track's suggested volume source. On 2026-10-31 that was about 30% of all Intents volume. For total Intents volume, use `fct_intents_daily`.
- Rows hold users' wallet addresses and run to about 14,000 a day, and raw pages would add about 450 KB per 1,000 rows. So each UTC day is walked once, counted and thrown away, and only the daily tally is stored.
- The date filter's bounds are exclusive and can reach just past the day, so rows are checked against the day as well. Pagination follows the last row's deposit address and memo.
- Statuses can still change, so the last 3 days are tallied again each night.
- The limit is 1 request per 5 seconds, and the last year alone is roughly 16,000 pages. So history arrives in this order, at 600 pages a night: the last 60 days in full, then one day a week back to 2024-11, then the days between. Check which days are present before summing.
- `appFees` entries are read as basis points of the value paid in. A fee recipient is named only if `registry/entities.csv` lists it; the rest are summed as `(other)`.
- A 1Click API key adds no market-wide data, so no fetcher uses one. Its quote and status endpoints serve a partner's own swaps, and account history needs a user session and an invitation.

### Can the Explorer replace NEAR's Dune dashboard?

No, but it can check part of it and adds detail the dashboard lacks. Figures below are for 2026-10-29 to 10-31, the first days compared.

| On the dashboard | From the Explorer? | Evidence | Held elsewhere |
|---|---|---|---|
| Total volume | Only part | 1Click was 27.9% of all Intents volume | DefiLlama, revenue.near.org |
| Public volume | Most of it | 1Click was 68.9% of NearBlocks' public volume | NearBlocks |
| Confidential volume | No | On 10-31, no finished 1Click swap used a confidential route, against $47.42M on the dashboard | Only as all minus public |
| Total fees | Most of it | 1Click app fees were 80.5% of all fees on the two complete days | DefiLlama, revenue.near.org |
| Fees by channel | 1Click channels only | SwapKit was 75.5% of 1Click fees, against 73.5% of the dashboard's all-time list | Nowhere else |
| Volume by asset | Only part | wNEAR: $1.5M paid in on 1Click, $13.6M on the dashboard | NearBlocks, public only |
| Volume by blockchain | Only part | Chains can be read from asset ids, for 1Click only | NearBlocks, public only |
| TVL, by asset and by type | No | The Explorer has no balances | DefiLlama, and revenue.near.org for confidential TVL |

### Dune
- Everything from Dune is derived from the [NEAR Intents dashboard](https://dune.com/near/near-intents), created by @near, and says so: gold tables carry a `derived_from` column, and each manifest note repeats it. NEAR uploads the data behind the dashboard, so nothing here checks it independently.
- Results are public and readable without logging in, but [Dune's terms](https://dune.com/terms) bar bots, scrapers and access other than its own interface. They allow copying public content with credit to its creator, and they don't say whether that covers query results. So readings are dated, credited and taken by hand, and nothing fetches the dashboard on a schedule.
- To take a reading:
  1. Open the dashboard in your own browser, with the Network tab of the developer tools open.
  2. Scroll until every widget has loaded.
  3. Save the Network tab as a HAR file, using the sanitized option if your browser offers it.
  4. Run `python -m tools.record_dune_reading <file.har> <date> "<how it was read>"`. See how many widgets were saved, and how many were partial.
- The tool keeps each widget's response exactly as received, and leaves headers, cookies and the page's signature behind. The date can't be later than `data/PINNED`, so move the pin first if it is. Keep the HAR file out of the repository; `.gitignore` covers it.
- `fct_dune_dashboard_results` holds every row of every widget. Widgets that matter get a typed table such as `fct_dune_intents_asset_daily`.
- Each reading of the asset widget covers about 30 days, so one reading every few weeks keeps that series continuous.
- A reading's all-time tiles stand still, so `dq_reconciliation` compares them with the other sources on the reading's last full day, the day before the snapshot, which is what the tiles covered. Comparing them with the latest day drifted about 0.3% a day and failed the nightly checks on 2026-11-04 and 11-05, until this was changed.
- Free access is view-only with no API, so the official fetcher needs a key on a plan or trial with API access. It skips cleanly without one.
- `near.balances` and `near.circulating_supply` were stale as of the 2026-10 research, and a NEAR data gap ran from 2026-02-28 to 03-19. Check before querying them.
- The first stored reading, in `dune_public/near_intents_dashboard`, was taken by an AI-driven browser and should be replaced by hand: see `registry/sources.csv`.

### Bitwise NEAR ETF (NRR)
- [Bitwise's page](https://nrretf.com) embeds the share count, NEAR in trust, daily NAV and market price, and a list of the trust's wallets. It shows only the current share count and no history. Its dates can differ by section, so each figure is stored with its own date.
- Flow is the change in shares times NAV. SoSoValue's reported flows work out to the same thing: on every day tested, the flow divided by NAV lands on a whole basket of 10,000 shares, the size set in the [prospectus](https://www.sec.gov/Archives/edgar/data/0002067111/000121390026103106/ea0306486-424b3_bitwise.htm).
- Nearly all of the listed wallets delegate to `bitwise_2.poolv1.near`, and the fund is nearly the whole pool, so one `get_accounts` call at a past block reads its NEAR for that day. Only the listed wallets are stored. Other delegators are people's own wallets, so they are kept as a total.
- The chain settles about one trading day after the trade and nets orders against each other. For example, +60,000 shares on 10-26 and −200,000 on 10-27 appear on chain as −150,000 on 10-28 and +10,000 on 10-29. So `fct_etf_nrr_daily` answers what traded on a day, and `fct_etf_nrr_chain_daily` answers what reached the chain.
- Three checks tie these together. Whole baskets settled on chain add up to exactly the fund's share count, chain NEAR is within about 0.2% of the fund's figure, and the seed baskets in the prospectus appear on chain on 2026-09-28. The gap in NEAR may be fees the fund still owes on its rewards; that has not been confirmed.
- History before the first saved snapshot is in `registry/etf_nrr_history.csv`, with a link and a basis on each row: 13 days use a flow reported by SoSoValue, 4 use the gap between two of its cumulative figures, and 7 use baskets settled on chain the next trading day. Those 7, from 10-01 to 10-09, are estimates: the total through 10-12 is $153,000, or 0.2%, below SoSoValue's. From the first snapshot on, flows come directly from Bitwise's share count.
- A missed night loses that day's share count for good, and the next reading's flow covers both days. The chain table is unaffected, because a past block can be read later.
- SoSoValue's own site refuses scripts, so its numbers come by hand from news reports. Those reports contain slips: ChainCatcher printed the 10-23 cumulative figure as $8.82629M and not $88.2629M. A data test holds each reported net-assets figure to shares times NAV.
- The first pool read is stored in the 2026-11-01 snapshot even though it was read on 2026-11-02. It reads only blocks up to the pin, and past blocks do not change. The manifest's `fetched_at` shows the real date.
- Bitwise's terms limit copying site content, so only figures and the wallet list are stored, never the page. See `registry/sources.csv` for what this means before going public.
- Other NEAR products are not tracked: Bitwise's European staking ETP, 21Shares, Virtune, Valour and Grayscale's trust. No daily share count or wallet list was found for them, and their published asset figures were old and did not always agree. One wallet holds 17.9M NEAR in `bitwise_1.poolv1.near` and one holds 10.4M in `svrn_bitwise.poolv1.near`. They could be the European ETP and SVRN, but neither has been confirmed, so neither is counted here.

## Tried and rejected

| Source | Why not |
|---|---|
| CoinGecko, GeckoTerminal | Terms bar storing or reproducing data, which a reproducible repository must do |
| Binance | HTTP 451 from this project's build machine |
| DefiLlama bridges | Paid |
| BigQuery `crypto_near_mainnet_us` | Not connected. Its freshness is unknown: the loader reads NEAR Lake, which stopped on 2026-03-24. Adding it needs a Google account and would give full distinct-signer and by-contract history |
| NEAR Lake S3, Pagoda API, Flipside, Mintbase GraphQL, Artemis legacy API | Dead or deprecated, per the earlier research |
| Pikespeak | Needs a registered key; not connected |
