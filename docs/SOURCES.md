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

Confidential Intents appear only in the NEAR family. Nothing here checks them independently, so treat them as self-reported.

The strongest checks are the ones that cross families. See [RECONCILIATION.md](RECONCILIATION.md), where `independence` marks each comparison.

## Notes per source

### NearBlocks
- v3 daily endpoints return at most 365 days per call. `limit` counts days, not rows, and `date=` returns a single day. History therefore grows with each stored snapshot.
- Legacy `/v1/charts` is the only full daily history back to 2020-07-21, and `/v1` is marked for eventual removal. The bronze copy protects against that.
- v3 `stats.circulating_supply` equals total supply, which is wrong. Circulating supply comes from `/v1` instead.
- v1 and v3 `active_accounts` disagree by about 1.8x and neither is documented. Gold keeps both and calls neither "daily active users".
- Prices are stamped at 00:00 UTC, which makes the value on day D the close of day D-1. Gold moves them back one day, after which they match the other price sources within about 0.1%.
- `tvl-stats` is a different measure from DefiLlama's chain TVL, about a third of it.
- All 16 MPC operators show `tee.status = none` at NearBlocks, while NEAR says Chain Signatures run inside TEEs. A blank here may only mean NearBlocks has no attestation data. Check the contract before claiming anything.

### DefiLlama
- Intents fees and revenue come from NEAR's Dune datasets, not an independent count. Read the [adapter](https://github.com/DefiLlama/dimension-adapters/blob/master/fees/near-intents/index.ts) before citing them.
- Revenue means NEAR and wNEAR swept into three wallets, excluding hops between them. Sweeps are periodic, so a single day's revenue can exceed that day's fees.
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

### Archival RPC
- `block`, `view_account` and `call_function` work at old heights.
- `validators` by `epoch_id` worked for an epoch in May 2026 and returned `UNKNOWN_EPOCH` for one in October 2024, so validator history is partial.
- Calls hit HTTP 429 quickly. The free RPC host recognises a FastNear key, but the archival host shows no sign of it, so archival calls keep the keyless pace.

### Neardata
- A block is about 265 KB, so raw blocks are counted and thrown away.
- The published limit is 180 requests per minute, but three parallel workers hit HTTP 429 from this machine. The sampler runs one request at a time.
- Sample results are estimates. `fct_receiver_sample_daily` keeps `blocks_sampled` on every row.

### Intents Explorer API
- Covers 1Click swaps only, despite being the track's suggested volume source. On 2026-10-31 that was about 30% of all Intents volume. For total Intents volume, use `fct_intents_daily`.
- Rows hold users' wallet addresses and run to about 14,000 a day, and raw pages would add about 450 KB per 1,000 rows. So each UTC day is walked once, counted and thrown away, and only the daily tally is stored.
- The date filter's bounds are exclusive and can reach just past the day, so rows are checked against the day as well. Pagination follows the last row's deposit address and memo.
- Statuses can still change, so the last 3 days are tallied again each night. Older days fill in newest first, 500 pages a night, because the limit is 1 request per 5 seconds.
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
- Free access is view-only with no API, so the official fetcher needs a key on a plan or trial with API access. It skips cleanly without one.
- `near.balances` and `near.circulating_supply` were stale as of the 2026-10 research, and a NEAR data gap ran from 2026-02-28 to 03-19. Check before querying them.
- The first stored reading, in `dune_public/near_intents_dashboard`, was taken by an AI-driven browser and should be replaced by hand: see `registry/sources.csv`.

## Tried and rejected

| Source | Why not |
|---|---|
| CoinGecko, GeckoTerminal | Terms bar storing or reproducing data, which a reproducible repository must do |
| Binance | HTTP 451 from this project's build machine |
| DefiLlama bridges | Paid |
| BigQuery `crypto_near_mainnet_us` | Not connected. Its freshness is unknown: the loader reads NEAR Lake, which stopped on 2026-03-24. Adding it needs a Google account and would give full distinct-signer and by-contract history |
| NEAR Lake S3, Pagoda API, Flipside, Mintbase GraphQL, Artemis legacy API | Dead or deprecated, per the earlier research |
| Pikespeak | Needs a registered key; not connected |
