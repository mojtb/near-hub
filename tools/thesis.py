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
from tools.horizon import horizon

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
CUT = trim(pct(float(ramp["annual_issuance_rate"])))
CUT_WHEN = (f"once the voted cut of issuance to {CUT} is in force" if ramp["status"] == "passed_vote_not_in_force"
            else f"at the end of HSP-029's ramp to {CUT}")
# Every scenario row, for the table under "How far away", and the years to break even at each pace (tools/horizon.py,
# which the dashboard reads too, so both print the same years)
scenarios = {(r["scenario_id"], r["capture_case"]): r for r in rows("select * from gold.fct_deflation_scenarios")}
paces = horizon(con)
pace_now = {r["scenario_id"]: r for r in paces if r["pace"] == "measured"}
growth = pace_now["current"]["growth_a_year"]
# The break-even multiple on the NEAR the wallets received over the 30 days, at each day's price: NEAR created less
# burned, over NEAR received. The Supply page computes the same (BILL.mult in site/index.html), so the two agree.
received_multiple = ((dilution["minted_30d_near"] - dilution["burn_30d_near"]) / dilution["revenue_inflow_30d_near"]
                     if dilution["revenue_inflow_30d_near"] else None)
received_price = (dilution["revenue_inflow_30d_usd"] / dilution["revenue_inflow_30d_near"]
                  if dilution["revenue_inflow_30d_near"] else None)
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
# NEAR's public BigQuery dataset, the source the sample prompt names: how it compares with NearBlocks, and who the day's
# function calls came from on the newest day read.
bq = {r["check_id"]: r for r in rows("""
    select check_id, cast(value_a as bigint) as a, cast(value_b as bigint) as b from gold.dq_reconciliation
    where check_id in ('chain_txns_days_equal_bigquery_vs_nearblocks', 'chain_signers_days_equal_bigquery_vs_nearblocks')""")}
bq_top = one("""
    select date_day, contract_id, signers, signer_share from gold.fct_bigquery_contract_daily
    where date_day = (select max(date_day) from gold.fct_bigquery_contract_daily) and rank_by_signers = 1""")
bq_intents = one(f"""
    select signers from gold.fct_bigquery_contract_daily where contract_id = 'intents.near' and date_day = date '{bq_top["date_day"]}'""")
bq_span = one("select min(date_day) as first_day, cast(count(distinct date_day) / 7 as integer) as weeks from gold.fct_bigquery_contract_daily")

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
    "to tell a correlation of 0.20 from chance), or a test on signers by application. The warehouse holds that count from "
    f"{day(bq_span['first_day'])} (`gold.fct_bigquery_contract_daily`), {bq_span['weeks']} weeks so far, too few to test.",
    f"- On the other usage claim: {signers_now['now']:,.0f} accounts a day signed a transaction over the newest 30 days. "
    f"The claim that signers are falling stops holding above {signers_now['bar']:,.0f} a day.",
    "",
    "What these sources cannot compute, so it is not on the site: daily active people (both account counts follow one game "
    "and one wallet app); who stands behind the HOT, Sweat and Kai-Ching accounts, which are named from their account ids "
    "alone; and new accounts once NearBlocks switches /v1 off on 22 November 2026.",
    "",
    "The prompt names the NEAR BigQuery public dataset, and the warehouse queries it (the SQL is in `ingest/sql/bigquery/`). "
    f"The chain counts on the site are NearBlocks', and BigQuery checks them day for day: over the {bq['chain_txns_days_equal_bigquery_vs_nearblocks']['b']} "
    f"days read, the two count the same transactions on {bq['chain_txns_days_equal_bigquery_vs_nearblocks']['a']} and the same "
    f"distinct signers on {bq['chain_signers_days_equal_bigquery_vs_nearblocks']['a']}. BigQuery also counts accounts by "
    f"contract and accounts that come back, which the Usage page charts: on {day(bq_top['date_day'])}, {pct(bq_top['signer_share'])} of the accounts that "
    f"signed a function call called `{bq_top['contract_id']}`, and {bq_intents['signers']:,.0f} called `intents.near` "
    "(`gold.fct_bigquery_contract_daily`).",
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


def signed(v: float, digits: int = 0) -> str:
    return ("+" if v >= 0 else "−") + pct(abs(v), digits)


def years(y) -> str:
    """A cell of the horizon table: None when volume is not growing, 0 when today's volume is already enough."""
    return "never at this pace" if y is None else "already enough" if y == 0 else f"{y:.1f}"


# The verdict: where the case stands on the settled day, and how far away the break-even is at the measured pace. It
# reads the offset, the two break-even multiples and the years from the data, so each state has its own wording.
m_now, m_cut = scenario["current"]["breakeven_volume_multiple"], scenario["hsp029_end_state"]["breakeven_volume_multiple"]
y_now, y_cut = pace_now["current"]["years_to_breakeven"], pace_now["hsp029_end_state"]["years_to_breakeven"]
price_day = scenario["current"]["as_of_date"]
NEEDS = "The long case needs the fees NEAR's revenue wallets receive and the gas burned to match the new NEAR the chain creates."
if dilution["offset_share"] >= 1:
    verdict = (f"**The gap has closed.** {NEEDS} Over the 30 days to {day(settled)} they came to {pct(dilution['offset_share'])} "
               "of it, so they match it. Whether that lasts turns on the price, the fee rate and NEAR's share of fees, which "
               "this file does not forecast.")
else:
    if m_now <= 1:
        match = (f"At NEAR's close on {day(price_day)}, today's Intents volume would already be enough to match it: the "
                 f"break-even multiple is {m_now:.1f}×.")
        pace_line = ""
    else:
        match = (f"To match it, Intents volume has to be {m_now:.1f}× today's, " +
                 (f"or {m_cut:.1f}× {CUT_WHEN}." if m_cut > 1 else f"and {CUT_WHEN}, today's volume would be enough ({m_cut:.1f}×)."))
        if growth is None or growth <= 0:
            pace_line = (f" Volume {'fell ' + pct(-growth, 0) if growth and growth < 0 else 'did not grow'} over the last year, "
                         "so at this pace the gap does not close.")
        else:
            pace_line = (f" Volume grew {pct(growth, 0)} over the last year; at that pace, with the price and NEAR's share of "
                         f"fees unchanged, that is about {y_now:.1f} years away" + (f", or {y_cut:.1f} after the cut." if y_cut else "."))
    verdict = (f"**Not yet.** {NEEDS} Over the 30 days to {day(settled)} they offset {pct(dilution['offset_share'])} of it. "
               f"{match}{pace_line} That is arithmetic, not a forecast: [How far away](#how-far-away) sets out the sums.")
# The first objection of anyone who knows NEAR: new NEAR goes to stakers, so who is diluted?
real = dilution["real_staking_yield_rate"]
staking = (f"New NEAR is paid mostly to stakers: {pct(dilution['staked_share'], 0)} of supply is staked and earns "
           f"{pct(dilution['nominal_staking_yield_rate'])} a year, {signed(real, 1).lstrip('+')} after dilution, so " +
           ("the dilution falls on NEAR that is not staked." if real > 0 else
            "even a staker is diluted, and NEAR that is not staked more so.")
           if dilution["nominal_staking_yield_rate"] is not None and dilution["staked_share"] is not None else "")

# How far away: the years at each pace, and every scenario row
PACE_NAMES = {"measured": "as measured"}
horizon_rows = [
    f"| {signed(r['growth_a_year'])}{', ' + PACE_NAMES[r['pace']] if r['pace'] in PACE_NAMES else ''}"
    f"{' (doubling)' if r['growth_a_year'] == 1 else ''} | {years(r['years_to_breakeven'])} | "
    f"{years(next(q for q in paces if q['pace'] == r['pace'] and q['scenario_id'] == 'hsp029_end_state')['years_to_breakeven'])} |"
    for r in paces if r["scenario_id"] == "current"]
CASES = ["measured", "at_50_pct", "at_70_pct", "at_100_pct"]
scenario_rows = [
    f"| {pct(scenarios[('current', k)]['capture_rate']) + ', as measured' if k == 'measured' else trim(pct(scenarios[('current', k)]['capture_rate']))} | "
    f"{scenarios[('current', k)]['breakeven_volume_multiple']:.2f}× | {scenarios[('hsp029_end_state', k)]['breakeven_volume_multiple']:.2f}× | "
    f"{signed(scenarios[('current', k)]['net_inflation_rate_at_current_volume'], 2)} | "
    f"{signed(scenarios[('hsp029_end_state', k)]['net_inflation_rate_at_current_volume'], 2)} |" for k in CASES]
grown = pace_now["current"]
growth_words = ("did not change" if not growth else f"grew {pct(growth, 0)}" if growth > 0 else f"fell {pct(-growth, 0)}")
at_close = signed(scenarios[("current", "measured")]["net_inflation_rate_at_current_volume"], 2).lstrip("+")
how_far = [
    "## How far away",
    "",
    f"Intents volume over the 30 days to {day(grown['as_of_date'])} was {usd(grown['volume_30d_usd'])}, against "
    f"{usd(grown['volume_30d_year_earlier_usd'])} over the same 30 days a year before, so it {growth_words} in a year.",
    "",
    f"Years until Intents volume reaches the break-even multiple, {m_now:.1f}× today and {m_cut:.1f}× after the cut to "
    f"{CUT}, if it grows at the measured pace or at a round one (`tools/horizon.py`):",
    "",
    f"| Growth of Intents volume a year | Years to break even, issuance as now | Years after the cut to {CUT} |",
    "|---|---|---|",
    *horizon_rows,
    "",
    "The multiple itself turns on NEAR's share of fees. These are the eight rows of `gold.fct_deflation_scenarios`, at the "
    f"share measured over the 30 days and at three higher ones, for issuance as now ({pct(dilution['gross_inflation_rate'], 2)} "
    f"of supply a year) and at {CUT}: the break-even multiple, and how fast the NEAR outside the wallets would grow a year "
    "at today's volume.",
    "",
    f"| NEAR's share of fees | Multiple, issuance as now | Multiple, at {CUT} | Growth at today's volume, issuance as now | "
    f"Growth, at {CUT} |",
    "|---|---|---|---|---|",
    *scenario_rows,
    "",
    *([f"The growth columns count the NEAR the wallets would receive at the close of ${scenario['current']['price_usd']:.2f} on "
       f"{day(price_day)}, so the measured row's {at_close} differs from the {pct(dilution['net_inflation_rate'], 2)} in "
       "The claim, which counts the NEAR they received at each day's price.", ""]
      if at_close != pct(dilution["net_inflation_rate"], 2) else []),
    f"All of this is arithmetic with the price, the fee rate and NEAR's share of fees held as measured on {day(price_day)}, "
    "and not a forecast. Issuance is paid in NEAR, so its value in dollars rises with the price, while revenue is charged "
    "in dollars and does not: a higher price moves the break-even further away, and a lower one brings it closer.",
    "",
]

# The two Limits that the count leans on: how the unlock result counts lockups that never switched transfers on, and
# the results near their bars that count for the case today, with the count if they all reversed.
unlocks = by_id["unlocks_are_behind"]
strict = one("""select transfers_never_enabled_near as never, date_day,
                       1 - circulating_share_of_total + transfers_never_enabled_near
                           / (circulating_supply_near / circulating_share_of_total) as share
                from gold.fct_circulating_supply_daily order by date_day desc limit 1""")
over_bar = strict["share"] > unlocks["threshold"] if unlocks["comparison"] == "<=" else strict["share"] < unlocks["threshold"]
unlock_line = (f"- The unlock result rests on a definition. Lockups whose owners never switched transfers on held "
               f"{near(strict['never'])} on {day(strict['date_day'])}, and they count as unlocked, as in NEAR Explorer. "
               f"Counted as locked, the share still locked would be {figure(strict['share'], unlocks['unit'])}, "
               + (f"over the bar of {WORDS[unlocks['comparison']]} {figure(unlocks['threshold'], unlocks['unit'], True)}, and "
                  f"the claim would {'fail' if unlocks['status'] == 'holds' else 'hold'}." if over_bar else
                  f"still inside the bar of {WORDS[unlocks['comparison']]} {figure(unlocks['threshold'], unlocks['unit'], True)}."))
NEAR_BAR = {"near_fees_outgrew_every_peer": "fee growth against peers", "zcash_is_on_a_fifth_of_volume": "Zcash's share of 1Click volume",
            "unlocks_are_behind": "the share of supply still locked"}
leaning = [by_id[k] for k in NEAR_BAR if by_id[k]["stands"] == "for"]
ALL = {1: "It counts", 2: "Both count", 3: "All three count"}
IF_ALL = {1: "if it reversed", 2: "if both reversed", 3: "if all three reversed"}
named = [f"{NEAR_BAR[c['claim_id']]} ({figure(c['value'], c['unit'])} against a bar of {WORDS[c['comparison']]} "
         f"{figure(c['threshold'], c['unit'], True)})" for c in leaning]
lean_line = (f"- The count leans on results that sit close to their bars or on a definition: "
             f"{', '.join(named[:-1]) + ' and ' + named[-1] if len(named) > 1 else named[0]}. {ALL[len(leaning)]} for the "
             f"case today; {IF_ALL[len(leaning)]}, the count would be {tally['for'] - len(leaning)} for and "
             f"{tally['against'] + len(leaning)} against.") if leaning else None
# What follows from the revenue tripwire when it trips
revenue_check = by_id["revenue_reaches_the_wallets"]
revenue_tripped = (
    "Because the revenue check fails, the revenue figures in this file are what NEAR's revenue wallets received on chain" +
    (f" (DefiLlama's count of the wallets, which their transfers confirm within {wallets['diff_pct']:.2f}%)"
     if wallets["status"] == "agree" else "") +
    f", not what NEAR reports. The wallets received {figure(revenue_check['value'], revenue_check['unit'])} less than NEAR's "
    "own monthly series says, and that series stays unexplained until a cause for the gap is published."
) if revenue_check["status"] == "fails" else None

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
    "## The verdict",
    "",
    verdict,
    "",
    *([staking, ""] if staking else []),
    "## The claim",
    "",
    f"Over the 30 days to {day(settled)}, NEAR created {near(dilution['minted_30d_near'])}, which is "
    f"{pct(dilution['gross_inflation_rate'], 2)} of supply a year. Gas burned and the NEAR its revenue wallets received "
    f"came to {pct(dilution['offset_share'])} of that: {received_points:.1f}% received and held by the wallets, "
    f"{share_points - received_points:.1f}% burned. **The long case is that this gap closes:** NEAR Intents keeps "
    "growing, NEAR keeps a larger share of the fees charged on it, and issuance falls to 1.6% a year.",
    "",
    f"On today's numbers the gap has {'closed' if dilution['offset_share'] >= 1 else 'not closed'}. Only the burned part leaves supply, so total supply grows "
    f"{pct(supply_growth, 2)} a year, and the NEAR outside the revenue wallets grows {pct(dilution['net_inflation_rate'], 2)}. "
    f"At the fee rate and the share of fees measured over those 30 days, and at NEAR's close of "
    f"${scenario['current']['price_usd']:.2f} on {day(price_day)}, Intents volume would have to be "
    f"{scenario['current']['breakeven_volume_multiple']:.1f}× what it is for the wallets to receive as much NEAR as is "
    f"created net of burn, or {scenario['hsp029_end_state']['breakeven_volume_multiple']:.1f}× once issuance is {CUT}. " +
    (f"Counted on the NEAR the wallets actually received over the 30 days, at each day's price (${received_price:.2f} a NEAR "
     f"on average), the multiple today is {received_multiple:.1f}× (NEAR created less burned, over NEAR received): NEAR "
     f"closed {'below' if received_price > scenario['current']['price_usd'] else 'above'} that average, so at the close the "
     f"same fees bring in {'more' if received_price > scenario['current']['price_usd'] else 'less'} NEAR. "
     if received_multiple is not None else "") + ramp_line,
    "",
    f"The verdict above is where the case stands on today's data, not a forecast of where it goes. The warehouse holds {tested} claims the data can settle: the "
    "links the case rests on, in order, and the risks to it, each with a measurement and a bar. "
    f"**{tally['for']} support the long case and {tally['against']} count against it**. The count is not a vote: the claims do "
    "not weigh the same, and the one that decides the case, how far revenue is from covering issuance, is among those "
    f"{by_id['a_doubling_of_volume_reaches_deflation_after_the_cut']['stands']}. "
    f"{COUNT[tally['open']].capitalize()} more claims cannot be tested yet and are listed apart.",
    "",
    *how_far,
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
    *([revenue_tripped, ""] if revenue_tripped else []),
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
    unlock_line,
    *([lean_line] if lean_line else []),
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
