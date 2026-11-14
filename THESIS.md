# The long case for NEAR, and what the data says about it

_Written by `make thesis` from the warehouse pinned at 2026-11-12: data through 11 Nov 2026, fees and revenue settled through 9 Nov 2026. Every figure is read from the warehouse, so none is typed. To change a claim or its bar, edit `registry/claims.csv`; to change the wording, edit `tools/thesis.py`._

The same scorecard, with a chart and the query behind every claim, is on the dashboard at [nearhub.tech](https://nearhub.tech).

## The verdict

**Not yet.** The long case needs the fees NEAR's revenue wallets receive and the gas burned to match the new NEAR the chain creates. Over the 30 days to 9 Nov 2026 they offset 16.1% of it. To match it, Intents volume has to be 5.2× today's, or 3.3× once the voted cut of issuance to 1.6% is in force. Volume grew 60% over the last year; at that pace, with the price and NEAR's share of fees unchanged, that is about 3.5 years away, or 2.6 after the cut. That is arithmetic, not a forecast: [How far away](#how-far-away) sets out the sums.

New NEAR is paid mostly to stakers: 45% of supply is staked and earns 5.0% a year, 2.5% after dilution, so the dilution falls on NEAR that is not staked.

## The claim

Over the 30 days to 9 Nov 2026, NEAR created 2.69M NEAR, which is 2.50% of supply a year. Gas burned and the NEAR its revenue wallets received came to 16.1% of that: 15.1% received and held by the wallets, 1.0% burned. **The long case is that this gap closes:** NEAR Intents keeps growing, NEAR keeps a larger share of the fees charged on it, and issuance falls to 1.6% a year.

On today's numbers the gap has not closed. Only the burned part leaves supply, so total supply grows 2.47% a year, and the NEAR outside the revenue wallets grows 2.10%. At the fee rate and the share of fees measured over those 30 days, and at NEAR's close of $3.62 on 9 Nov 2026, Intents volume would have to be 5.2× what it is for the wallets to receive as much NEAR as is created net of burn, or 3.3× once issuance is 1.6%. Counted on the NEAR the wallets actually received over the 30 days, at each day's price ($4.53 a NEAR on average), the multiple today is 6.6× (NEAR created less burned, over NEAR received): NEAR closed below that average, so at the close the same fees bring in more NEAR. HSP-029, which would set the ramp to 1.6%, has passed its vote and is not yet in force: by its own text validators must adopt it first, so 1.6% is a scenario and not a schedule.

The verdict above is where the case stands on today's data, not a forecast of where it goes. The warehouse holds 19 claims the data can settle: the links the case rests on, in order, and the risks to it, each with a measurement and a bar. **10 support the long case and 9 count against it**. The count is not a vote: the claims do not weigh the same, and the one that decides the case, how far revenue is from covering issuance, is among those against. Four more claims cannot be tested yet and are listed apart.

## How far away

Intents volume over the 30 days to 9 Nov 2026 was $3.73B, against $2.33B over the same 30 days a year before, so it grew 60% in a year.

Years until Intents volume reaches the break-even multiple, 5.2× today and 3.3× after the cut to 1.6%, if it grows at the measured pace or at a round one (`tools/horizon.py`):

| Growth of Intents volume a year | Years to break even, issuance as now | Years after the cut to 1.6% |
|---|---|---|
| +60%, as measured | 3.5 | 2.6 |
| +25% | 7.4 | 5.4 |
| +50% | 4.1 | 3.0 |
| +100% (doubling) | 2.4 | 1.7 |

The multiple itself turns on NEAR's share of fees. These are the eight rows of `gold.fct_deflation_scenarios`, at the share measured over the 30 days and at three higher ones, for issuance as now (2.50% of supply a year) and at 1.6%: the break-even multiple, and how fast the NEAR outside the wallets would grow a year at today's volume.

| NEAR's share of fees | Multiple, issuance as now | Multiple, at 1.6% | Growth at today's volume, issuance as now | Growth, at 1.6% |
|---|---|---|---|---|
| 31.6%, as measured | 5.24× | 3.34× | +2.00% | +1.10% |
| 50% | 3.31× | 2.11× | +1.73% | +0.83% |
| 70% | 2.36× | 1.51× | +1.43% | +0.53% |
| 100% | 1.65× | 1.05× | +0.98% | +0.08% |

The growth columns count the NEAR the wallets would receive at the close of $3.62 on 9 Nov 2026, so the measured row's 2.00% differs from the 2.10% in The claim, which counts the NEAR they received at each day's price.

A year of new NEAR is worth the issuance rate times NEAR's market value, so what reaches the token in a year (the fees the revenue wallets receive plus the gas burned) matches issuance when the market value is about 40× that amount at today's rate, or about 62× at 1.6%. On 9 Nov 2026 it was 198×. At today's price, then, what reaches the token has to be about 5× what it is: the 5.2× above, counted another way.

All of this is arithmetic with the price, the fee rate and NEAR's share of fees held as measured on 9 Nov 2026, and not a forecast. Issuance is paid in NEAR, so its value in dollars rises with the price, while revenue is charged in dollars and does not: a higher price moves the break-even further away, and a lower one brings it closer.

## Evidence for

These results support the long case: a bull claim that holds, or a bear claim that fails.

| Claim | Result | Measured | Bar | As of |
|---|---|---|---|---|
| NEAR Intents is taking a growing share of on-chain trading | Bull claim holds | **+52.6%** | at least 0% | 31 Oct 2026 |
| Intents volume was at least $2B in each of the last three complete months | Bull claim holds | **$3.20B** | at least $2B | 31 Oct 2026 |
| NEAR's wallets receive a rising share of the fees charged on Intents | Bull claim holds | **+8.6 points** | at least 0 points | 31 Oct 2026 |
| More partners pay meaningful fees than a quarter ago | Bull claim holds | **+48.3%** | at least 0% | 31 Oct 2026 |
| The revenue wallets keep the NEAR they receive: under 5% of it has left | Bull claim holds | **1.3%** | at most 5% | 11 Nov 2026 |
| Burn and the NEAR the revenue wallets receive are a larger share of issuance than in the 90 days before | Bull claim holds | **+7.4 points** | at least 0 points | 9 Nov 2026 |
| The unlock schedule is spent: under 1% of supply is still locked | Bull claim holds | **0.2%** | at most 1% | 11 Nov 2026 |
| NEAR's application fees grew faster than any peer's over the last three complete months | Bull claim holds | **+0.1 points** | at least 0 points | 31 Oct 2026 |
| Zcash is on one side of at least a fifth of 1Click volume | Bear claim fails | **17.7%** | at least 20% | 31 Oct 2026 |
| Dollars held in NEAR Intents are higher than a quarter ago | Bull claim holds | **+55.4%** | at least 0% | 31 Oct 2026 |

## Evidence against

These results count against it: a bull claim that fails, or a bear claim that holds.

| Claim | Result | Measured | Bar | As of |
|---|---|---|---|---|
| The revenue NEAR reports arrives on chain: what its wallets received is within 10% of its own monthly series | Bull claim fails | **15.7%** | at most 10% | 11 Nov 2026 |
| The Bitwise ETF took in more NEAR than the chain created over the last 30 days | Bull claim fails | **0.12×** | at least 1× | 11 Nov 2026 |
| At the end of HSP-029's ramp to 1.6%, a doubling of Intents volume would let revenue and burn match the NEAR that is created | Bull claim fails | **3.34×** | at most 2× | 9 Nov 2026 |
| NEAR trades above the median peer on application fees | Bear claim holds | **1.65×** | at least 1× | 9 Nov 2026 |
| One partner supplies more than half of 1Click's fees | Bear claim holds | **69.4%** | at least 50% | 31 Oct 2026 |
| Fewer accounts sign transactions on NEAR than six months ago | Bear claim holds | **−50.0%** | at most −10% | 11 Nov 2026 |
| Intents volume leads network usage: usage rises in the weeks after volume does | Bull claim fails | **+0.20** | at least 0.37 | 8 Nov 2026 |
| The ten largest pools hold more than a third of the stake | Bear claim holds | **36.2%** | at least 33.3% | 11 Nov 2026 |
| Less NEAR sits in liquid staking than a year ago | Bear claim holds | **−24.0%** | at most 0% | 12 Nov 2026 |

## What the data cannot settle yet

- **NEAR AI has paying users.** NEAR AI publishes no usage or revenue figures, and its one on-chain trace, escrow.ai.near, has a single caller.
- **A few market makers fill most Intents volume.** No public source gives counts or shares of market makers; the data here holds only the distinct callers of intents.near.
- **The NEAR Foundation's liquid NEAR is a large overhang on the float.** The Foundation's last published holding is 305M NEAR on 2024-01-11 (registry/near_supply_readings.csv); nothing newer is public.
- **Other cross-chain swap protocols are as large as NEAR Intents and can take its flow.** The services that do the same job do not report one kind of volume. Some report the swaps they settled and others the tokens sent through them across chains, which counts a transfer of the same token too, so whether one is as large as NEAR Intents depends on which kind counts (fct_swap_services_daily). The Intents page sets them side by side.

## What would change my mind

Three claims are kept as tripwires. The case weakens when one of them stops holding. One of the three does not hold today.

- **Intents volume was at least $2B in each of the last three complete months.** Measured $3.20B against a bar of at least $2B, on 31 Oct 2026: it holds.
- **The revenue NEAR reports arrives on chain: what its wallets received is within 10% of its own monthly series.** Measured 15.7% against a bar of at most 10%, on 11 Nov 2026: it fails.
- **The revenue wallets keep the NEAR they receive: under 5% of it has left.** Measured 1.3% against a bar of at most 5%, on 11 Nov 2026: it holds.

Because the revenue check fails, the revenue figures in this file are what NEAR's revenue wallets received on chain (DefiLlama's count of the wallets, which their transfers confirm within 0.29%), not what NEAR reports. The wallets received 15.7% less than NEAR's own monthly series says, and that series stays unexplained until a cause for the gap is published.

Beyond those, two figures decide the case. The share of new NEAR received by the wallets or burned, 16.1% now, has to reach 100%. At 100% the NEAR outside the wallets stops growing; total supply stops growing only if what the wallets hold is burned. The break-even multiple, 5.2× now, has to reach 1×.

## What to watch

What is due next, in date order, and what each means for the case.

- **16 Nov 2026.** HSP-029's timelock is due to end. That does not start the cut to 1.6%, which validators must still adopt, and until the cut is in force the break-even multiple is the 5.2× for issuance as now, not the 3.3× at the end of its ramp.
- **22 Nov 2026.** NearBlocks switches /v1 off and with it its count of distinct signers, the measure behind the claim that signers are falling. NEAR's public BigQuery dataset, which counted the same distinct signers on every one of the 680 days both sources hold, can carry the count on.
- **30 Nov 2026.** November 2026 closes. The 8 claims that read complete months, 7 of them counting for the case today, then read the three months to 30 Nov 2026 in place of those to 31 Oct 2026.
- **30 Dec 2026.** Sweat Wallet is due to end in its present form. Its relayer carried 25.0% of the transactions outside the batch streams over the 30 days to 11 Nov 2026, so another break in the transaction counts is likely, and it is one reason the usage claim reads signers and not transactions.
- **No date set.** HSP-029's cut to 1.6% comes into force. Its text puts a grace period of 90 days before the first basis point comes off and then lowers the cap in a straight line over 24 months; the one precedent here, the proposal "Remove the NEAR Developer Gas Rebate", came into force on 4 Nov 2026, 124 days after its vote ended on 3 Jul 2026.

## The sample prompt's hypothesis

The sample prompt for this track gives a working hypothesis to test: "cross-chain volume through NEAR Intents is a better leading indicator of real network usage than token price". It is on the scorecard as `intents_volume_leads_usage`, and it fails. The test reads 29 weekly changes, from the week of 20 Apr 2026 to the week of 2 Nov 2026 (`gold.fct_usage_lead_correlations`).

- One or two weeks ahead, the largest link between Intents volume and any of four usage measures is +0.20 (distinct signers), and the token price's is +0.43 (gas paid). With 29 weeks, chance alone gives up to ±0.37.
- The NEAR price 1 week ahead of gas paid is outside that band on weeks cut on Mondays. Cut on each of the seven weekdays it reads between +0.05 and +0.43, and it is outside the band on one of the seven.
- In the same week both move with transactions (+0.69 for volume and +0.46 for the price) and neither with signers (0.00 and −0.22).
- What would change this reading: a lead above the band once more weeks exist (97 weeks are needed to tell a correlation of 0.20 from chance), or a test on signers by application. The warehouse holds that count from 3 Apr 2026 (`gold.fct_bigquery_contract_daily`), 32 weeks so far, too few to test.
- On the other usage claim: 62,272 accounts a day signed a transaction over the newest 30 days. The claim that signers are falling stops holding above 112,100 a day.

What these sources cannot compute, so it is not on the site: daily active people (both account counts follow one game and one wallet app); who stands behind the HOT, Sweat and Kai-Ching accounts, which are named from their account ids alone; and new accounts once NearBlocks switches /v1 off on 22 Nov 2026.

The prompt names the NEAR BigQuery public dataset, and the warehouse queries it (the SQL is in `ingest/sql/bigquery/`). The chain counts on the site are NearBlocks', and BigQuery checks them day for day: over the 680 days read, the two count the same transactions on 678 and the same distinct signers on 680. BigQuery also counts accounts by contract and accounts that come back, which the Usage page charts: on 11 Nov 2026, 97.2% of the accounts that signed a function call called `game.hot.tg`, and 221 called `intents.near` (`gold.fct_bigquery_contract_daily`).

## Limits

- The set was cut from 29 claims to 20 on 2026-11-11 by four rules: a claim sits on the chain the thesis argues (Intents grows, NEAR keeps more of its fees, the revenue reaches the token, supply growth slows, and the price paid) or names a risk to it; no measurement is scored twice; a claim must be able to hold and able to fail; and a claim about Intents reads three complete months together, so that one month does not decide it.
- On 2026-11-12 one claim was added, the working hypothesis in the track's sample prompt (that Intents volume leads network usage), and the usage claim was pointed at distinct signers in place of transactions; two more came from the review of the Capital page, one for the case (dollars held in NEAR Intents are rising) and one against it (less NEAR sits in liquid staking than a year ago). The same day the security claim was pointed at the ten largest pools' share of the stake in place of the number of validator pools, because the pools that left in 60 days held under 1% of the stake.
- The thresholds were written between 2026-11-10 and 2026-11-12 with the readings of those days in view, so they are round bars for what each claim's wording means, not predictions; why_this_threshold gives the reason for each. The claims file as submitted is timestamped (`registry/claims.csv.ots`, an OpenTimestamps proof) and the submitted state is tagged `submission-2026-11-14`, so a later change to a bar can be seen.
- The ETF claim is read over the last 30 days, 0.12× what the chain issued. Since its first trading day the fund has taken in 3.86×, but that figure leans on its start: 75% of the NEAR arrived in its first week, and it has handed back 2.56M NEAR since its peak on 26 Oct 2026.
- The share of new NEAR received by the wallets or burned is up on the 90 days before, but it has not climbed steadily: over the 270 days to 9 Nov 2026 the 30-day share moved between 7.8% and 25.5%.
- The closest call on the list is "NEAR's application fees grew faster than any peer's over the last three complete months": measured +0.1 points against a bar of at least 0 points. If that one result reversed, the count would be 9 for and 10 against.
- The fee-growth claim rests on two nearly equal numbers: NEAR's application fees grew 91.95% and Solana's 91.84%, the last three complete months against the three before. DefiLlama restates these series after the fact. Scored on each of the 12 nightly reads taken since that quarter closed, the claim held on 7 and failed on 5, with the gap between −2.3 points and +0.2 points (`silver.stg_defillama__chain_fees` keeps every read).
- Zcash is near its bar too: 17.7% of 1Click volume over three months against a bar of 20%, and 22.8% in October 2026 alone.
- The unlock result rests on a definition. Lockups whose owners never switched transfers on held 19.35M NEAR on 11 Nov 2026, and they count as unlocked, as in NEAR Explorer. Counted as locked, the share still locked would be 1.6%, over the bar of at most 1%, and the claim would fail.
- The count leans on results that sit close to their bars or on a definition: fee growth against peers (+0.1 points against a bar of at least 0 points), Zcash's share of 1Click volume (17.7% against a bar of at least 20%) and the share of supply still locked (0.2% against a bar of at most 1%). All three count for the case today; if all three reversed, the count would be 7 for and 12 against.
- Most results that count for the case read the same months: 7 of the 10 read the three complete months to 31 Oct 2026, and 6 of them measure NEAR Intents. A strong or weak quarter for Intents would move those 6 together, so they are fewer independent pieces of evidence than their number suggests.
- Intents volume and fees are NEAR's own published series. What its revenue wallets received is checked against the chain: DefiLlama's all-time figure is $9.83M and the same sum rebuilt from wallet transfers, valued as DefiLlama values it at each day's close, is $9.80M, 0.29% apart, so the two agree. DefiLlama takes its figure from NEAR's own count of the same wallets, so this confirms the count and nothing more. NEAR's own monthly revenue series says $11.69M; valued on the day each payment arrived, the wallets received $9.85M, 15.7% less, and no cause has been published.
- Market caps are not on one supply rule: NEAR's counts nearly all of its supply, and each peer's counts what its project reports as circulating. Most of what DefiLlama counts as a chain's app fees is passed on to others. So the valuation result leans on its basis: NEAR is 1.65 times the median peer on app fees and 1.47 times on the part of fees that applications keep.
- 38% of Intents volume in October 2026 settled confidentially. NEAR's own dashboard still gives that volume by chain and by asset, and no public record shows which account swapped what. That share is rising, so less of Intents can be checked from outside.
- Across the warehouse, 88 comparisons between independent sources agree, 22 agree but share an upstream, and 15 differ. Each difference is explained in `docs/RECONCILIATION.md`.
- This is an entry in the NEAR HACKATHON Investment Thesis track, and prizes are paid in NEAR, so the author could gain exposure to the asset analysed here. It is an independent project, not affiliated with the NEAR Foundation, and it is not investment advice.

## Check it yourself

1. Run `make setup`, `make warehouse` and `make verify`. See every check pass.
2. Run `make query SQL="select claim_id, side, value, comparison, threshold, status from gold.fct_thesis_scorecard"`. See the rows behind the tables above.
3. Run `make thesis`. See this file written again with the same figures.
4. Run `make site` and open `site/index.html`. Its front page shows the same scorecard, and each claim links to its chart and query.

The query behind each claim is a select named by its `claim_id` in `warehouse/models/gold/thesis/fct_thesis_scorecard.sql`.

## How each claim is measured

| Claim id | Side | Pillar | What is measured | Why this bar |
|---|---|---|---|---|
| `intents_is_gaining_share` | bull | growth | Intents volume over the DEX volume of the six peer chains in the last three complete months, over the same share in the three months before, minus 1 (fct_intents_unit_economics_monthly, fct_peer_daily) | Any gain counts. Quarters are compared and not years, because a year earlier Intents had barely started and a yearly gain would flatter it |
| `volume_stayed_above_2bn_a_month` | bull | watch | The lowest volume_usd of the last three complete months (fct_intents_unit_economics_monthly) | The bar the author's earlier draft of this thesis named as what would change its author's mind (the near-deflation-clock scaffold; see the README's disclosures) |
| `capture_is_rising` | bull | value capture | Revenue over fees in the last three complete months, minus the same in the three months before (fct_intents_unit_economics_monthly) | Any rise counts. Three months are read together because revenue is swept in lumps, so one month alone can sit far from the trend |
| `fee_base_is_widening` | bull | concentration | Partners with at least $10,000 of app fees in a month, counted over the last three complete months, over the same count for the three months before, minus 1; swaps that name no partner are left out (fct_intents_channel_economics_monthly) | Any growth counts. $10,000 a month is the size at which a partner is a business and not a trial |
| `revenue_reaches_the_wallets` | bull | watch | One minus what the Intents contract paid the revenue wallets, with USDC at one dollar on the day it arrived and NEAR at the transfer's value, over revenue.near.org's monthly revenue series, all time (fct_wallet_transfers, fct_revenue_page_monthly) | The bar the author's earlier draft of this thesis named as what would change its author's mind (the near-deflation-clock scaffold; see the README's disclosures) |
| `revenue_wallets_keep_their_near` | bull | watch | NEAR sent out of the three revenue wallets, not counting moves between them, over NEAR they received (fct_wallet_flows_daily, fct_revenue_inflows_daily) | Small enough to be operations rather than selling |
| `etf_took_in_more_than_issuance` | bull | demand | flow_to_issuance_30d_ratio on the newest trading day (fct_etf_absorption_daily) | More than issuance means a ratio of at least one. The 30 days count the fund's flow on its trading days and the issuance on every day. The same ratio since the fund's first trading day is cumulative_flow_to_issuance_ratio in the same table; it is not the test because with no flows at all it stays above one for months, so it says little about demand today |
| `offsets_are_rising` | bull | supply | Gas burned plus NEAR received by the revenue wallets, over NEAR created, across the 90 days to the newest settled day, minus the same across the 90 days before (fct_net_dilution_daily, three 30-day readings each) | Any rise counts. Ninety days are read to smooth single months. The base is the 90 days before, because a year earlier the wallets had received nothing and issuance was twice as high, so against that base the claim could not fail |
| `unlocks_are_behind` | bull | supply | 1 minus circulating_share_of_total on the newest day: what lockup contracts and the two Foundation lockup accounts still hold, over total supply (fct_circulating_supply_daily) | Under a hundredth of supply is too little to move the float. The test does not cover NEAR the Foundation holds unlocked, which is not published. Lockups whose owners never switched transfers on (19.35M NEAR, unchanged since July 2023) count as unlocked, as in NEAR Explorer; counted as locked they would put the share above the bar |
| `a_doubling_of_volume_reaches_deflation_after_the_cut` | bull | supply | breakeven_volume_multiple for scenario hsp029_end_state at the measured share of fees (fct_deflation_scenarios) | A doubling is the bar the claim names |
| `near_fees_outgrew_every_peer` | bull | growth | Change in application fees, the last three complete months against the three before, for NEAR minus the highest of the six peers (fct_peer_daily). Quarters are compared and not years, because a year earlier NEAR's fees had barely started and a yearly gain would flatter it. The Market page's question on fee growth shows the 90-day and the yearly figures beside it | Faster than every peer means a gap above zero against the best of them |
| `near_is_dearer_than_the_median_peer` | bear | valuation | NEAR's multiple on the app_fees basis over the median of the six peers', on the newest settled day (fct_valuation_multiples_daily). A year of fees is the last 30 days times 365/30, and each market cap is as its source reports it | Above the median means a ratio over one |
| `fees_depend_on_one_partner` | bear | concentration | The largest partner's share of 1Click app fees over the last three complete months (fct_intents_channel_economics_monthly) | More than half is what dependence on one partner means |
| `zcash_is_on_a_fifth_of_volume` | bear | concentration | Share of finished 1Click volume with ZEC as origin or destination, over the last three complete months of the daily run (fct_intents_1click_pair_daily) | The published share of ZEC alone was 9% of all volume; a fifth on either side is the bar for dependence. Three months are read together because the share moves by ten points from one month to the next |
| `usage_is_falling` | bear | usage | Mean distinct_signers over the newest 30 days over the 30 days ending 180 days earlier, minus 1 (fct_chain_daily). Accounts that only signed their own deletion are left out while NearBlocks /v1 reports them, which ends on 2026-11-22. About 60% of active accounts call one game, HOT's, so this count follows its players | A tenth fewer signers in half a year is a fall and not noise. Signers are read and not transactions, because the count of transactions without the batch streams was only lower with the Sweat relayer in it, and Sweat Wallet is due to end on 2026-12-30 |
| `intents_volume_leads_usage` | bull | usage | The largest correlation between week-on-week changes in Intents volume and in four usage measures one and two weeks later: transactions without the batch streams and the Sweat relayer, the same without HOT's game and Intents' own, distinct signers, and gas paid. Full weeks from 2026-04-20, cut on Mondays (fct_usage_lead_correlations). This is a common hypothesis about NEAR, which also asks whether volume leads better than the token price; the same table holds the price | With about 30 weekly changes, chance alone gives a correlation of up to 0.37 nineteen times in twenty, so only a link above that counts as a lead. The bar stays at 0.37 as weeks are added, which makes it harder to pass, not easier |
| `ten_pools_hold_a_third` | bear | security | The ten largest staking pools' share of all stake in the newest complete epoch (fct_validator_summary). These are pool accounts: the data does not record who runs a pool | The chain stops finalising if over a third of the stake goes offline or refuses, so that much in ten pools is the bar for concentration. The share was under a third on 16 of the 365 days to 2026-11-10, last on 2026-01-14, so the claim can fail. It replaced a claim on the number of validator pools on 2026-11-12: the pools that left in 60 days held under 1% of the stake, and the count moves by a dozen between two epochs of one day |
| `liquid_staking_is_shrinking` | bear | demand | NEAR staked through the liquid staking tokens stNEAR, LiNEAR and rNEAR on the newest day, over the same day a year earlier, minus 1 (fct_lst_snapshot) | Any fall over the year counts. Liquid staking is where the chain itself shows holders keeping NEAR at work, and what it pays halved when issuance was cut in October 2025. The figure was above zero until July 2026, so the claim can fail |
| `dollars_are_arriving_in_intents` | bull | growth | Mean value of stablecoins held in NEAR Intents, public and confidential balances together, over the last three complete months, over the same mean for the three months before, minus 1 (fct_dune_intents_tvl_asset_daily) | Any rise counts. Three complete months are read against the three before, as for every claim about Intents, so a dashboard that is read on request cannot leave a month half measured. The series is NEAR's own figure. The stablecoins the contract holds are read from the chain at each month end, and the two agree at every month end since the dashboard has carried every stablecoin the pool holds (intents_pool_dollars_month_ends_chain_vs_dune in dq_reconciliation) |
| `near_ai_has_paying_users` | bull | product | Not testable: NEAR AI publishes no usage or revenue figures, and its one on-chain trace, escrow.ai.near, has a single caller | – |
| `solvers_are_few` | bear | concentration | Not testable: no public source gives counts or shares of market makers; the data here holds only the distinct callers of intents.near | – |
| `foundation_float_is_an_overhang` | bear | supply | Not testable: the Foundation's last published holding is 305M NEAR on 2024-01-11 (registry/near_supply_readings.csv); nothing newer is public | – |
| `competitors_are_as_large` | bear | competition | Not testable: the services that do the same job do not report one kind of volume. Some report the swaps they settled and others the tokens sent through them across chains, which counts a transfer of the same token too, so whether one is as large as NEAR Intents depends on which kind counts (fct_swap_services_daily). The Intents page sets them side by side | – |
