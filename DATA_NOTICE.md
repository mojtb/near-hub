# Data notice

This project collects public data about the NEAR blockchain so that an investment case can be checked against it.
[THESIS.md](THESIS.md) states the case. This file is about the data under it: what is stored, where it came from, and
the terms it is held under.

## Not advice, and not a guarantee

- **This is not investment advice.** It is one author's reading of public data, published so that others can disagree
  with it from the same tables. The author may hold NEAR and may be paid in NEAR for this work.
- **No warranty.** Figures can be revised. Sources restate their own history, the newest days of fee and revenue data
  are provisional until they settle, and a reading taken by hand is only as new as the day it was taken. Every table
  says which day it covers and `dq_freshness` says how old each source is.
- **Independent.** This project is not affiliated with the NEAR Foundation, Bitwise, Dune, DefiLlama or any other
  source named below. Where a figure is a source's own report about itself, the tables, the dashboard and the thesis
  say so in those words.

## What is stored, and why

Every response is kept as it was saved, under `data/bronze/`: in full, or, where a source returns personal data or
very large pages, reduced before saving, with a manifest note that says how. Each file has the address it came from,
the day it was fetched and its SHA-256 hash in a manifest. `make verify` re-hashes all of them, so a reader can
confirm that the tables were built from the files in this repository and not from something edited afterwards.
Nothing is stored that was not public when it was read.

The tables hold accounts, contracts, repositories, protocols and counts. No column holds a person's name. Account ids
on a public blockchain are pseudonymous, and they are kept because they are the evidence: a reader who doubts a figure
can follow it to the account it came from. The governance forum's threads are stored as titles, dates and counts.
Until 2026-11-13 the nightly fetch kept the forum's public replies whole, with each post's author, username and text.
Those files were taken out of `main` on 2026-11-13; they remain in its earlier commits and on the `data/nightly`
branch. The developer tables count authors without naming them.

Three sources cannot be fetched by a script and are read by hand: the Bitwise fund's flows as news reports give them,
NEAR's published supply figures, and the protocol upgrades that changed a rate. NEAR's public dashboard on Dune has no
free API, so it is read as a page. Its three stored readings (2026-11-01, 11-10 and 11-12) were taken in a browser, on
request and never on a schedule, by an AI-driven browser at the author's instruction; one widget of the first was
copied by hand. Each reading is dated, credited and kept with the rest, and the pages that use it say when it was
taken.

## Sources

This table is generated from `registry/sources.csv`, and `make verify` fails if it stops matching. What each source
can and cannot tell you is in [docs/SOURCES.md](docs/SOURCES.md).

<!-- sources:start -->
| Source | What it gives this project | Its terms, as read when it was added | Terms page |
|---|---|---|---|
| `coinbase` | NEAR-USD daily candles | Terms page could not be read (HTTP 403) | [www.coinbase.com](https://www.coinbase.com/legal/market-data) |
| `coinmetrics` | Reference price and market cap of NEAR and its peers, and the reference price of five assets held in the NEAR Intents pool | Community data is CC BY-NC 4.0: attribution required and non-commercial use only | [gitbook-docs.coinmetrics.io](https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data) |
| `defillama` | TVL, fees, revenue, DEX volume, stablecoins, prices, the volume of other cross-chain swap services, and the daily price of three assets held in the NEAR Intents pool | Site terms bar republishing data in any form without permission and mirroring materials; public API use is allowed; no attribution clause found; API-specific terms not reviewed | [defillama.com](https://defillama.com/terms) |
| `dune` | Stored results of public queries | Official API use under Dune's terms; credit the query's creator | [docs.dune.com](https://docs.dune.com/learning/how-tos/pricing-faqs) |
| `dune_public` | Readings of NEAR's public Intents dashboard, kept with credit | Terms bar bots, scrapers and access other than Dune's interface, and bar copying or mirroring except as allowed; public content may be forked and copied with credit to its creator; query results are not addressed directly | [dune.com](https://dune.com/terms) |
| `fastnear` | Wallet transfers, holdings, top holders, transaction counts | No data license found on the pages read | [docs.fastnear.com](https://docs.fastnear.com/auth) |
| `github` | Repository statistics | Public repository metadata under GitHub's terms | [docs.github.com](https://docs.github.com/en/site-policy/github-terms/github-terms-of-service) |
| `gov` | Governance threads | Public forum; author names appear in search results | [gov.near.org](https://gov.near.org/) |
| `intents_explorer` | 1Click swaps counted per day | Partner API; the docs read on 2026-11-01 state no license or publishing terms | [docs.near-intents.org](https://docs.near-intents.org/integration/distribution-channels/1click-api/explorer/introduction) |
| `metapool` | Meta Pool metrics. No longer fetched, because nothing read them: stNEAR's figures come from its contract. The nights already fetched stay in bronze | Terms not reviewed | [validators.narwallets.com](https://validators.narwallets.com/metrics) |
| `near_supply_readings` | NEAR's published supply schedule, the Foundation's reported NEAR holdings and one market cap from a filing, read by hand, with a link per row | Short figures from NEAR's post, press reports and an SEC filing; registry/near_supply_readings.csv keeps only the numbers and a link | [near.org](https://near.org/blog/near-token-supply-and-distribution) |
| `nearblocks` | Daily chain, Intents, per-contract, per-token and wallet statistics, and the validator list | Free plan is marked personal use with attribution required; commercial use needs a paid plan | [nearblocks.io](https://nearblocks.io/apis) |
| `nearcatalog` | Project directory | Terms not reviewed | [nearcatalog.xyz](https://nearcatalog.xyz/) |
| `neardata` | Sample blocks | Public chain data; terms not reviewed | [neardata.xyz](https://neardata.xyz) |
| `nrr_fund` | Bitwise NEAR ETF (NRR): share count, NEAR held, NAV, market price and its wallet list | Terms effective 2022-06-06 give a personal-use license and bar copying or republishing site content, or public or commercial use, without written permission; they cover Bitwise's own sites and don't name nrretf.com; its robots.txt allows crawling | [bitwiseinvestments.com](https://bitwiseinvestments.com/terms-of-service) |
| `oneclick` | Supported token list with prices | Terms not reviewed | [docs.near-intents.org](https://docs.near-intents.org/) |
| `protocol_upgrades` | Protocol upgrades that changed a rate gold uses, dated to the block by archival EXPERIMENTAL_protocol_config reads, with the evidence on each row | Chain data read from a public node; registry/protocol_upgrades.csv keeps only versions, heights, times and rates | [docs.near.org](https://docs.near.org/api/rpc/protocol) |
| `revenue_page` | NEAR's own revenue and fee series | NEAR's public report; no license stated | [revenue.near.org](https://revenue.near.org/) |
| `rhea` | Pools and token prices | Terms not reviewed | [guide.rhea.finance](https://guide.rhea.finance/) |
| `rpc` | Protocol config, validators, contract state, archival blocks, and what intents.near held of named tokens at past blocks | Public chain data; provider terms not reviewed | [docs.near.org](https://docs.near.org/api/rpc/providers) |
| `sosovalue_news` | Bitwise NEAR ETF daily flows reported by SoSoValue, read by hand from news reports, with a link per row | SoSoValue's terms not reviewed; only dated figures from news reports are kept | [sosovalue.com](https://sosovalue.com/) |
<!-- sources:end -->

## Limits worth naming

- **Coin Metrics** community data is CC BY-NC 4.0: attribution is required and the use must be non-commercial. Its
  prices are used for NEAR, the peer chains and the assets held in the Intents pool.
- **NEAR's dashboard on Dune** is NEAR's own: NEAR uploads the data behind it, so those figures are self-reported, and
  every table built from them carries a `derived_from` column that says so. The readings were taken in a browser, on
  request and never on a schedule, by an AI-driven browser at the author's instruction (each manifest note says how),
  and credit the dashboard's creator, @near.
- **Bitwise's fund page** has terms that limit copying site content, so the page itself is not stored. Only dated
  figures are kept, and each row in `registry/etf_nrr_history.csv` says how it was reached.
- **DefiLlama's** site terms bar republishing its data without permission. Its responses are stored here so that the
  build can be reproduced and checked; they are not offered as a copy of its dataset.
- **NearBlocks'** free plan is marked personal use with attribution.
- **CoinGecko and GeckoTerminal** are not used. Their terms bar storing or reproducing their data, and the registry
  keeps a row for each so that the decision is on the record.

This repository's [LICENSE](LICENSE) covers the code. It does not cover the data under `data/`, which remains subject
to each source's own terms.

## Credit

NearBlocks, DefiLlama, FastNear, Neardata, revenue.near.org, Coin Metrics
([CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)), Coinbase, 1Click, Rhea, Meta Pool, GitHub,
NEAR Catalog, gov.near.org, the [NEAR Intents dashboard](https://dune.com/near/near-intents) by @near on Dune, Bitwise,
and SoSoValue through the news reports linked in `registry/etf_nrr_history.csv`.

## If you are a source and want something removed

Open an issue on this repository. Each source's responses sit in one folder, `data/bronze/<source>/`, and its row in
`registry/sources.csv` names it, so what came from a source can be found and removed together. Please say which source
you speak for and what you would like removed.
