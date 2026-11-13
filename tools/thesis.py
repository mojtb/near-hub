"""`make thesis`: write THESIS.md from the warehouse's claim scorecard.

  .venv/bin/python -m tools.thesis
Run after `make warehouse`. The warehouse is opened read-only. Every figure in THESIS.md is read from the warehouse
here (gold tables, and silver for the one line about nightly reads), so the file holds no typed number: to change a claim or its bar, edit registry/claims.csv; to change the
wording, edit this module. Running it twice in a row writes the same file.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

import duckdb

from tools.catalog import closest_call

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
OUT = ROOT / "THESIS.md"

if not WAREHOUSE.exists():
    sys.exit("data/warehouse.duckdb is missing: run `make warehouse` first")
con = duckdb.connect(str(WAREHOUSE), read_only=True)
con.execute("set threads = 1")


def rows(sql: str) -> list[dict]:
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def one(sql: str) -> dict:
    return rows(sql)[0]


def trim(text: str) -> str:
    """12.0% reads 12%, and 2.0x reads 2x."""
    return re.sub(r"\.0+(?=\D|$)", "", text)


def usd(v: float, digits: int = 2) -> str:
    for size, unit in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(v) >= size:
            return f"${v / size:.{digits}f}{unit}"
    return f"${v:.0f}"


def near(v: float) -> str:
    return f"{v / 1e6:.2f}M NEAR" if abs(v) >= 1e6 else f"{v:,.0f} NEAR"


def pct(v: float, digits: int = 1) -> str:
    return f"{v * 100:.{digits}f}%"


def day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def figure(v, unit: str, bar: bool = False) -> str:
    """A claim's value in its own unit. A bar is written shorter: no sign on a share, no spare zeros."""
    if v is None:
        return "–"
    a = abs(v)
    if unit == "share":
        return trim(pct(v)) if bar else pct(v, 3 if a < 0.001 else 1)
    if unit == "rate":
        if bar:
            return ("−" if v < 0 else "") + trim(pct(a))
        return ("+" if v >= 0 else "−") + pct(a, 2 if a < 0.1 else 1)
    if unit == "share points":
        return trim(f"{v * 100:.1f}") + " points" if bar else ("+" if v >= 0 else "−") + f"{a * 100:.1f} points"
    if unit == "multiple":
        return trim(f"{v:.1f}") + "×" if bar else f"{v:.2f}×"
    if unit == "USD":
        return usd(v, 0 if bar else 2)
    if unit == "correlation":
        return f"{a:.2f}" if bar else ("+" if v >= 0 else "−") + f"{a:.2f}"
    return f"{v:,.0f}"


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


WORDS = {">=": "at least", "<=": "at most"}
COUNT = ["none", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
order = {r["claim_id"]: i for i, r in enumerate(csv.DictReader((ROOT / "registry" / "claims.csv").open()))}
claims = sorted(rows("""
    select s.claim_id, s.side, c.pillar, s.claim, s.value, s.comparison, s.threshold, c.unit, s.status, s.as_of_date,
           c.test, c.why_this_threshold as why
    from gold.fct_thesis_scorecard s join gold.dim_claim c using (claim_id)"""), key=lambda r: order[r["claim_id"]])
for c in claims:
    c["stands"] = "open" if c["status"] == "not_testable" else "for" if (c["side"] == "bull") == (c["status"] == "holds") else "against"
tally = {k: sum(1 for c in claims if c["stands"] == k) for k in ("for", "against", "open")}
tested = tally["for"] + tally["against"]

settled = one("select max(date_day) as d from gold.fct_intents_daily where not is_fee_revenue_provisional")["d"]
last_day = one("select max(date_day) as d from gold.fct_supply_daily")["d"]
pinned = (ROOT / "data" / "PINNED").read_text().strip()
dilution = one(f"select * from gold.fct_net_dilution_daily where date_day = date '{settled}'")
# The share of new NEAR has two parts, and only the burned part leaves supply: the revenue wallets hold what they
# receive. So total supply grows by what is minted less what is burned, and net_inflation_rate is the growth of the
# NEAR outside the wallets. The parts are printed in points so that they add up to the share as printed.
received_share = dilution["revenue_inflow_30d_near"] / dilution["minted_30d_near"]
burned_share = dilution["burn_30d_near"] / dilution["minted_30d_near"]
supply_growth = dilution["gross_inflation_rate"] * (1 - burned_share)
share_points = round(dilution["offset_share"] * 1000) / 10
received_points = round(received_share * 1000) / 10
scenario = {r["scenario_id"]: r for r in rows("select * from gold.fct_deflation_scenarios where capture_case = 'measured'")}
ramp = next(r for r in csv.DictReader((ROOT / "registry" / "issuance_scenarios.csv").open()) if r["scenario_id"] == "hsp029_end_state")
month = one("""select month_start, confidential_volume_share, capture_rate from gold.fct_intents_unit_economics_monthly
               where is_month_complete order by month_start desc limit 1""")
# NEAR's own monthly revenue series beside what the Intents contract paid its revenue wallets, counted on the day it
# arrived (native USDC at one dollar, NEAR at the transfer's value): the measure of revenue_reaches_the_wallets
USDC_ON_NEAR = "nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1"
series = one(f"""
    select (select sum(revenue_usd) from gold.fct_revenue_page_monthly) as booked,
           sum(case when asset_id = '{USDC_ON_NEAR}' then amount_token else amount_usd end) as received
    from gold.fct_wallet_transfers
    where account_id in (select distinct account_id from gold.fct_revenue_inflows_daily)
      and direction = 'in' and counterparty_id = 'intents.near'
      and asset_id in ('native:near', 'nep141:wrap.near', '{USDC_ON_NEAR}')""")
# NEAR's multiple over the median peer's on the newest settled day, on app fees and on the part applications keep
premium = {r["basis"]: r["ratio"] for r in rows("""
    select basis, max(multiple) filter (where chain_id = 'near') / median(multiple) filter (where chain_id <> 'near') as ratio
    from gold.fct_valuation_multiples_daily
    where basis in ('app_fees', 'app_revenue')
      and date_day = (select max(date_day) from gold.fct_valuation_multiples_daily where not is_provisional)
    group by 1""")}
wallets = one("""select value_a, value_b, diff_pct, status from gold.dq_reconciliation
                 where check_id = 'intents_revenue_all_time_defillama_vs_wallets'""")
recon = one("""select count(*) filter (where status = 'agree' and independence = 'independent') as independent_agree,
                      count(*) filter (where status = 'agree' and independence <> 'independent') as shared_agree,
                      count(*) filter (where status = 'differs') as differs
               from gold.dq_reconciliation""")
catalog = {t["table"]: t for t in json.loads((ROOT / "data" / "gold" / "_catalog.json").read_text())}
claim_notes = [s.strip() for s in re.split(r"(?<=[a-z])\.\s", catalog["dim_claim"]["description"])]
bars_note = next((s for s in claim_notes if "thresholds were written" in s), None)
set_note = next((s for s in claim_notes if "was cut from" in s), None)
added_note = next((s for s in claim_notes if "one claim was added" in s), None)
by_id = {c["claim_id"]: c for c in claims}

# Where a claim's row says less than it seems to. Each figure is read here, so none is typed.
etf = one("""
    with f as (select * from gold.fct_etf_absorption_daily)
    select arg_max(cumulative_flow_near, date_day) as held_near,
           max(cumulative_flow_near) as peak_near,
           arg_max(date_day, cumulative_flow_near) as peak_day,
           (select arg_max(cumulative_flow_near, date_day) from f
            where date_day <= date_trunc('week', (select min(date_day) from f)) + interval 6 day) as first_week_near,
           arg_max(flow_to_issuance_30d_ratio, date_day) as ratio_30d,
           arg_max(cumulative_flow_to_issuance_ratio, date_day) as ratio_all
    from f""")
offset_range = one(f"""select min(offset_share) as low, max(offset_share) as high from gold.fct_net_dilution_daily
                       where date_day > date '{settled}' - 270 and date_day <= date '{settled}'""")
zec_month = one("""
    select sum(amount_in_usd) filter (where origin_symbol = 'ZEC' or destination_symbol = 'ZEC') / sum(amount_in_usd) as v,
           max(date_day) as d
    from gold.fct_intents_1click_pair_daily
    where is_in_daily_run and cast(date_trunc('month', date_day) as date)
          = (select max(month_start) from gold.fct_intents_channel_economics_monthly where is_month_complete)""")
zec = by_id["zcash_is_on_a_fifth_of_volume"]
# The claim nearest its bar, by one rule for every claim (tools/catalog.py), and the tally if that result turned
close = closest_call(con)
closest = by_id[close["claim_id"]]
# The fee-growth claim: each side's growth over the scorecard's two quarters, and how the claim would have scored on
# every nightly read of DefiLlama's fees since the newer quarter closed. Silver keeps each read; gold keeps the newest.
fee = by_id["near_fees_outgrew_every_peer"]
QUARTERS = f"""date_day > date '{fee['as_of_date']}' - interval 6 month and date_day <= date '{fee['as_of_date']}'"""
NEWER = f"""date_day > date '{fee['as_of_date']}' - interval 3 month"""
fee_sides = rows(f"""
    select p.chain_id, sum(fees_usd) filter (where {NEWER}) / sum(fees_usd) filter (where not ({NEWER})) - 1 as change
    from gold.fct_peer_daily p where {QUARTERS} group by 1 order by change desc""")
fee_near = next(r for r in fee_sides if r["chain_id"] == "near")
fee_peer = next(r for r in fee_sides if r["chain_id"] != "near")
fee_reads = one(f"""
    with per_read as (
        select f.snapshot_date, p.chain_id,
               sum(f.value_usd) filter (where {NEWER}) / sum(f.value_usd) filter (where not ({NEWER})) - 1 as change
        from silver.stg_defillama__chain_fees f join registry.peers p using (llama_chain)
        where f.data_type = 'dailyFees' and {QUARTERS} and f.snapshot_date > date '{fee['as_of_date']}'
        group by 1, 2
    ), gaps as (
        select snapshot_date, max(change) filter (where chain_id = 'near') - max(change) filter (where chain_id <> 'near') as gap
        from per_read group by 1
    )
    select count(*) as reads, count(*) filter (where gap >= {fee['threshold']}) as held, min(gap) as low, max(gap) as high from gaps""")
thin = [
    f"- The ETF claim is read over the last 30 days, {etf['ratio_30d']:.2f}× what the chain issued. Since its first trading day "
    f"the fund has taken in {etf['ratio_all']:.2f}×, but that figure leans on its start: {pct(etf['first_week_near'] / etf['held_near'], 0)} "
    f"of the NEAR arrived in its first week, and it has handed back {near(etf['peak_near'] - etf['held_near'])} since its peak on "
    f"{day(etf['peak_day'])}.",
    f"- The share of new NEAR received by the wallets or burned is up on the 90 days before, but it has not climbed steadily: over the 270 days to {day(settled)} "
    f"the 30-day share moved between {pct(offset_range['low'])} and {pct(offset_range['high'])}.",
    f"- The closest call on the list is \"{closest['claim']}\": measured {figure(closest['value'], closest['unit'])} against a bar of "
    f"{WORDS[closest['comparison']]} {figure(closest['threshold'], closest['unit'], True)}. If that one result reversed, the count "
    f"would be {close['if_reversed'][0]} for and {close['if_reversed'][1]} against.",
    f"- The fee-growth claim rests on two nearly equal numbers: NEAR's application fees grew {pct(fee_near['change'], 2)} and "
    f"{fee_peer['chain_id'].capitalize()}'s {pct(fee_peer['change'], 2)}, the last three complete months against the three before. "
    f"DefiLlama restates these series after the fact. Scored on each of the {fee_reads['reads']} nightly reads taken since that "
    f"quarter closed, the claim held on {fee_reads['held']} and failed on {fee_reads['reads'] - fee_reads['held']}, with the gap "
    f"between {figure(fee_reads['low'], fee['unit'])} and {figure(fee_reads['high'], fee['unit'])} "
    "(`silver.stg_defillama__chain_fees` keeps every read).",
    f"- Zcash is near its bar too: {figure(zec['value'], zec['unit'])} of 1Click volume over three months against a bar of "
    f"{figure(zec['threshold'], zec['unit'], True)}, and {pct(zec_month['v'])} in {zec_month['d']:%B %Y} alone.",
]


# The working hypothesis in the track's sample prompt, on weeks cut on Mondays: the largest link with each leader one
# or two weeks ahead of usage, the same-week links, and how far the one figure outside the band of chance moves when
# the weeks are cut on other weekdays.
USAGE_NAMES = {"transactions": "transactions", "other_transactions": "transactions outside the known apps",
               "signers": "distinct signers", "gas_paid": "gas paid"}
LEADER_NAMES = {"intents_volume": "Intents volume", "near_price": "the NEAR price"}


def corr(v: float) -> str:
    """A correlation to two places; one that rounds to zero carries no sign."""
    return f"{abs(v):.2f}" if abs(v) < 0.005 else ("+" if v >= 0 else "−") + f"{abs(v):.2f}"


lead = {r["leader"]: r for r in rows("""
    select leader, max(correlation) as best, arg_max(usage_measure, correlation) as measure,
           arg_max(lead_weeks, correlation) as lead_weeks, max(weeks) as weeks, max(chance_bound) as bound,
           min(first_week) as first_week, max(last_week) as last_week
    from gold.fct_usage_lead_correlations
    where week_shift_days = 0 and lead_weeks in (1, 2) group by 1""")}
same = {(r["leader"], r["usage_measure"]): r["correlation"] for r in rows("""
    select leader, usage_measure, correlation from gold.fct_usage_lead_correlations
    where week_shift_days = 0 and lead_weeks = 0""")}
outside = [r for r in rows("""
    select leader, usage_measure, lead_weeks, correlation, chance_bound from gold.fct_usage_lead_correlations
    where week_shift_days = 0 and lead_weeks in (1, 2) and abs(correlation) > chance_bound
    order by abs(correlation) desc""")]
cuts = [one(f"""
    select min(correlation) as low, max(correlation) as high,
           count(*) filter (where abs(correlation) > chance_bound) as cuts_outside, count(*) as cuts
    from gold.fct_usage_lead_correlations
    where leader = '{r['leader']}' and usage_measure = '{r['usage_measure']}' and lead_weeks = {r['lead_weeks']}""") for r in outside]
signers_now = one("""
    select avg(distinct_signers) filter (where date_day > e.d - 30) as now,
           0.9 * avg(distinct_signers) filter (where date_day <= e.d - 180 and date_day > e.d - 210) as bar
    from gold.fct_chain_daily, (select max(date_day) as d from gold.fct_chain_daily where distinct_signers is not null) e""")


def weeks_to_see(r: float) -> int:
    """The fewest weekly changes with which a correlation of r is more than chance alone gives."""
    n = 5
    while True:
        df = n - 2
        t = 1.96 + 2.4 / df
        if t / (df + t * t) ** 0.5 <= r:
            return n
        n += 1


vol, px = lead["intents_volume"], lead["near_price"]
hypothesis = [
    "## The sample prompt's hypothesis",
    "",
    "The sample prompt for this track gives a working hypothesis to test: \"cross-chain volume through NEAR Intents is a "
    "better leading indicator of real network usage than token price\". It is on the scorecard as "
    f"`intents_volume_leads_usage`, and it {by_id['intents_volume_leads_usage']['status']}. The test reads {vol['weeks']} weekly "
    f"changes, from the week of {day(vol['first_week'])} to the week of {day(vol['last_week'])} "
    "(`gold.fct_usage_lead_correlations`).",
    "",
    f"- One or two weeks ahead, the largest link between Intents volume and any of four usage measures is {corr(vol['best'])} "
    f"({USAGE_NAMES[vol['measure']]}), and the token price's is {corr(px['best'])} ({USAGE_NAMES[px['measure']]}). With "
    f"{vol['weeks']} weeks, chance alone gives up to ±{vol['bound']:.2f}.",
    *[f"- {LEADER_NAMES[r['leader']][0].upper() + LEADER_NAMES[r['leader']][1:]} {r['lead_weeks']} week{'s' if r['lead_weeks'] > 1 else ''} "
      f"ahead of {USAGE_NAMES[r['usage_measure']]} is outside that band on weeks cut on Mondays. Cut on each of the seven "
      f"weekdays it reads between {corr(c['low'])} and {corr(c['high'])}, and it is outside the band on "
      f"{COUNT[c['cuts_outside']]} of the {COUNT[c['cuts']]}." for r, c in zip(outside, cuts)],
    f"- In the same week both move with transactions ({corr(same[('intents_volume', 'transactions')])} for volume and "
    f"{corr(same[('near_price', 'transactions')])} for the price) and neither with signers "
    f"({corr(same[('intents_volume', 'signers')])} and {corr(same[('near_price', 'signers')])}).",
    f"- What would change this reading: a lead above the band once more weeks exist ({weeks_to_see(0.2)} weeks are needed "
    "to tell a correlation of 0.20 from chance), or a count of NEAR signers by application, which the warehouse does not hold.",
    f"- On the other usage claim: {signers_now['now']:,.0f} accounts a day signed a transaction over the newest 30 days. "
    f"The claim that signers are falling stops holding above {signers_now['bar']:,.0f} a day.",
    "",
    "What these sources cannot compute, so it is not on the site: daily active people (both account counts follow one game "
    "and one wallet app); signers by application; who stands behind the HOT, Sweat and Kai-Ching accounts, which are named "
    "from their account ids alone; and new and deleted accounts once NearBlocks switches /v1 off on 22 November 2026. The "
    "prompt names the NEAR BigQuery public dataset; this warehouse does not query it. Its chain counts are NearBlocks', "
    "checked against a sample of blocks from Neardata.",
    "",
]


def reason(c: dict) -> str:
    """Why a claim cannot be tested, as dim_claim.test words it."""
    text = re.sub(r"^Not testable:\s*", "", c["test"]).rstrip(".")
    return text[:1].upper() + text[1:]


def table(side_rows: list[dict]) -> list[str]:
    out = ["| Claim | Result | Measured | Bar | As of |", "|---|---|---|---|---|"]
    for c in side_rows:
        result = f"{'Bull' if c['side'] == 'bull' else 'Bear'} claim {c['status']}"
        out.append(f"| {cell(c['claim'])} | {result} | **{figure(c['value'], c['unit'])}** | "
                   f"{WORDS[c['comparison']]} {figure(c['threshold'], c['unit'], True)} | {day(c['as_of_date'])} |")
    return out


watch = [c for c in claims if c["pillar"] == "watch"]
watch_failing = sum(1 for c in watch if c["status"] == "fails")
watch_line = (f"All {COUNT[len(watch)]} hold today." if not watch_failing else
              f"{COUNT[watch_failing].capitalize()} of the {COUNT[len(watch)]} {'does' if watch_failing == 1 else 'do'} not hold today.")
ramp_line = ("HSP-029, which would set the ramp to 1.6%, has passed its vote and is not yet in force: by its own text "
             "validators must adopt it first, so 1.6% is a scenario and not a schedule."
             if ramp["status"] == "passed_vote_not_in_force" else f"The 1.6% rate is HSP-029's end state; its status in the registry is `{ramp['status']}`.")

md: list[str] = [
    "# The long case for NEAR, and what the data says about it",
    "",
    f"_Written by `make thesis` from the warehouse pinned at {pinned}: data through {day(last_day)}, fees and revenue settled "
    f"through {day(settled)}. Every figure is read from the warehouse, so none is typed. To change a claim or its bar, edit "
    "`registry/claims.csv`; to change the wording, edit `tools/thesis.py`._",
    "",
    "The same scorecard, with a chart and the query behind every claim, is on the dashboard at "
    "[nearhub.tech](https://nearhub.tech).",
    "",
    "## The claim",
    "",
    f"Over the 30 days to {day(settled)}, NEAR minted {near(dilution['minted_30d_near'])}, which is "
    f"{pct(dilution['gross_inflation_rate'], 2)} of supply a year. Gas burned and the NEAR its revenue wallets received "
    f"came to {pct(dilution['offset_share'])} of that: {received_points:.1f}% received and held by the wallets, "
    f"{share_points - received_points:.1f}% burned. **The long case is that this gap closes:** NEAR Intents keeps "
    "growing, NEAR keeps a larger share of the fees charged on it, and issuance falls to 1.6% a year.",
    "",
    f"On today's numbers the gap has not closed. Only the burned part leaves supply, so total supply grows "
    f"{pct(supply_growth, 2)} a year, and the NEAR outside the revenue wallets grows {pct(dilution['net_inflation_rate'], 2)}. "
    f"At the fee rate and the share of fees measured over those 30 days, Intents volume would have to be "
    f"{scenario['current']['breakeven_volume_multiple']:.1f}× what it is for the wallets to receive as much NEAR as is "
    f"minted net of burn, or {scenario['hsp029_end_state']['breakeven_volume_multiple']:.1f}× once issuance is 1.6%. {ramp_line}",
    "",
    f"So this is a case with a test attached, not a forecast. The warehouse holds {tested} claims the data can settle: the "
    "links the case rests on, in order, and the risks to it, each with a measurement and a bar. "
    f"**{tally['for']} support the long case and {tally['against']} count against it**. The count is not a vote: the claims do "
    "not weigh the same, and the one that decides the case, how far revenue is from covering issuance, is among those against. "
    f"{COUNT[tally['open']].capitalize()} more claims cannot be tested yet and are listed apart.",
    "",
    "## Evidence for",
    "",
    "These results support the long case: a bull claim that holds, or a bear claim that fails.",
    "",
    *table([c for c in claims if c["stands"] == "for"]),
    "",
    "## Evidence against",
    "",
    "These results count against it: a bull claim that fails, or a bear claim that holds.",
    "",
    *table([c for c in claims if c["stands"] == "against"]),
    "",
    "## What the data cannot settle yet",
    "",
    *[f"- **{c['claim']}.** {reason(c)}." for c in claims if c["stands"] == "open"],
    "",
    "## What would change my mind",
    "",
    f"{COUNT[len(watch)].capitalize()} claims are kept as tripwires. The case weakens when one of them stops holding. {watch_line}",
    "",
    *[f"- **{c['claim']}.** Measured {figure(c['value'], c['unit'])} against a bar of {WORDS[c['comparison']]} "
      f"{figure(c['threshold'], c['unit'], True)}, on {day(c['as_of_date'])}: it {c['status']}." for c in watch],
    "",
    f"Beyond those, two figures decide the case. The share of new NEAR received by the wallets or burned, "
    f"{pct(dilution['offset_share'])} now, has to reach 100%. At 100% the NEAR outside the wallets stops growing; total supply "
    f"stops growing only if what the wallets hold is burned. The break-even multiple, "
    f"{scenario['current']['breakeven_volume_multiple']:.1f}× now, has to reach 1×.",
    "",
    *hypothesis,
    "## Limits",
    "",
    *([f"- {set_note}."] if set_note else []),
    *([f"- {added_note}."] if added_note else []),
    *([f"- {bars_note}."] if bars_note else []),
    *thin,
    f"- Intents volume and fees are NEAR's own published series. What its revenue wallets received is checked against the "
    f"chain: DefiLlama's all-time figure is {usd(wallets['value_a'])} and the same sum rebuilt from wallet transfers, valued as DefiLlama "
    f"values it at each day's close, is {usd(wallets['value_b'])}, {wallets['diff_pct']:.2f}% apart, so the two {wallets['status']}. DefiLlama takes its figure "
    f"from NEAR's own count of the same wallets, so this confirms the count and nothing more. NEAR's own monthly revenue series "
    f"says {usd(series['booked'])}; valued on the day each payment arrived, the wallets received {usd(series['received'])}, "
    f"{pct(1 - series['received'] / series['booked'])} less, and no cause has been published.",
    f"- Market caps are not on one supply rule: NEAR's counts nearly all of its supply, and each peer's counts what its project "
    f"reports as circulating. Most of what DefiLlama counts as a chain's app fees is passed on to others. So the valuation "
    f"result leans on its basis: NEAR is {premium['app_fees']:.2f} times the median peer on app fees and "
    f"{premium['app_revenue']:.2f} times on the part of fees that applications keep.",
    f"- {pct(month['confidential_volume_share'], 0)} of Intents volume in {month['month_start']:%B %Y} settled confidentially. "
    "NEAR's own dashboard still gives that volume by chain and by asset, and no public record shows which account swapped "
    "what. That share is rising, so less of Intents can be checked from outside.",
    f"- Across the warehouse, {recon['independent_agree']} comparisons between independent sources agree, {recon['shared_agree']} "
    f"agree but share an upstream, and {recon['differs']} differ. Each difference is explained in `docs/RECONCILIATION.md`.",
    "- This is an entry in the NEAR HACKATHON Investment Thesis track, and prizes are paid in NEAR, so the author could gain "
    "exposure to the asset analysed here. It is an independent project, not affiliated with the NEAR Foundation, and it is "
    "not investment advice.",
    "",
    "## Check it yourself",
    "",
    "1. Run `make setup`, `make warehouse` and `make verify`. See every check pass.",
    "2. Run `make query SQL=\"select claim_id, side, value, comparison, threshold, status from gold.fct_thesis_scorecard\"`. "
    "See the rows behind the tables above.",
    "3. Run `make thesis`. See this file written again with the same figures.",
    "4. Run `make site` and open `site/index.html`. Its front page shows the same scorecard, and each claim links to its chart and query.",
    "",
    "The query behind each claim is a select named by its `claim_id` in `warehouse/models/gold/thesis/fct_thesis_scorecard.sql`.",
    "",
    "## How each claim is measured",
    "",
    "| Claim id | Side | Pillar | What is measured | Why this bar |",
    "|---|---|---|---|---|",
    *[f"| `{c['claim_id']}` | {c['side']} | {c['pillar']} | {cell(c['test'])} | {cell(c['why'] or '–')} |" for c in claims],
    "",
]

OUT.write_text("\n".join(md))
print(f"wrote THESIS.md: {len(claims)} claims, {tally['for']} for, {tally['against']} against, {tally['open']} not testable, "
      f"settled through {settled}")
