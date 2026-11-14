"""`make site`, step 1: export the series the dashboard draws, from the warehouse to site/shared/data.js.

Run after `make warehouse`, which builds data/warehouse.duckdb and dbt's manifest:
  .venv/bin/python -m tools.site_data
The warehouse is opened read-only. Every number on the site comes from this file, so the page holds no typed figure.
"""
import csv
import json
import statistics
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
MANIFEST = ROOT / "warehouse" / "target" / "manifest.json"
OUT = ROOT / "site" / "shared" / "data.js"

for needed in (WAREHOUSE, MANIFEST):
    if not needed.exists():
        sys.exit(f"{needed.relative_to(ROOT)} is missing: run `make warehouse` first")

con = duckdb.connect(str(WAREHOUSE), read_only=True)
# One thread, and every list below is ordered down to a unique key, so two runs on one warehouse write the same file
con.execute("set threads = 1")


def rows(sql):
    cur = con.execute(sql)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def one(sql):
    return rows(sql)[0]


def clean(value, digits=4):
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        if value != value:
            return None
        # A sum over many rows is not the same to its last bits on every build, and a sum that lands on a half would
        # then round up on one build and down on the next. Fourteen significant digits are steady, so round from those.
        value = float(f"{value:.14g}")
        if abs(value) >= 1000:
            return round(value)
        return round(value, digits)
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return value


def table(sql, digits=4):
    return [{k: clean(v, digits) for k, v in r.items()} for r in rows(sql)]


def columns(sql, digits=4):
    data = table(sql, digits)
    return {k: [r[k] for r in data] for k in (data[0] if data else {})}


# Three cut-off days, all read from the data. The last full day for most series. Intents fees and revenue stop two
# days earlier, because those days can still be revised (is_fee_revenue_provisional). The Intents mix by chain and
# asset uses the window of the last hand reading of NEAR's Dune dashboard, so it can sit beside that reading's
# confidential share.
LAST_DAY = one("select max(date_day) d from gold.fct_supply_daily")["d"]
FEE_DAY = one("select max(date_day) d from gold.fct_intents_daily where not is_fee_revenue_provisional")["d"]
DUNE_READ = one("select max(snapshot_date) d from gold.fct_intents_dashboard_readings")["d"]
DUNE_DAY = one(f"select date '{DUNE_READ}' - interval 1 day d")["d"]
LAST, FEES, DUNE = f"date '{LAST_DAY}'", f"date '{FEE_DAY}'", f"date '{DUNE_DAY:%Y-%m-%d}'"
window = lambda end: f"date_day > {end} - interval 30 day and date_day <= {end}"
D30, F30, U30 = window(LAST), window(FEES), window(DUNE)
full_week = lambda end: f"date_trunc('week', date_day) + interval 6 day <= {end}"
# Whole weeks only, at both ends: a window of so many days back from `end` starts in the middle of a week on most days,
# and a first "week" of one day makes every chain look many times larger when the chart sets that week to 100.
whole_weeks = lambda end, days: (f"date_trunc('week', date_day) > date_trunc('week', {end} - interval {days} day) "
                                 f"and date_day <= {end} and {full_week(end)}")

weekly = columns(f"""
  with s as (select date_trunc('week', date_day) wk, sum(minted_near) minted, sum(burn_near) burn,
                    sum(treasury_reward_near) treasury, last(total_supply_near order by date_day) supply
             from gold.fct_supply_daily group by 1),
       c as (select date_trunc('week', date_day) wk, sum(txns) txns, avg(distinct_signers) active_v1,
                    avg(active_accounts_with_relayed) active_v3, sum(new_accounts) new_accounts
             from gold.fct_chain_daily group by 1),
       m as (select date_trunc('week', date_day) wk, last(price_usd order by date_day) price,
                    last(market_cap_usd order by date_day) mcap
             from gold.fct_market_daily group by 1),
       t as (select date_trunc('week', date_day) wk, last(tvl_usd order by date_day) tvl
             from gold.fct_peer_daily where chain_id = 'near' group by 1)
  select s.wk d, price, mcap, supply, minted, burn, treasury, txns, active_v1, active_v3, new_accounts, tvl
  from s left join c using (wk) left join m using (wk) left join t using (wk)
  where s.wk + interval 6 day <= {LAST}
  order by 1""")

# Intents volume and fees count every route, confidential included (revenue.near.org, with DefiLlama only on days the
# page lacks); swaps are NearBlocks' public count; revenue is DefiLlama's. Volume runs to the last full day: a day's
# all-route volume and its public volume have not changed after their first reading on any night the warehouse holds.
# Fees and revenue are left empty on the newest days, which can still be revised (is_fee_revenue_provisional).
# swaps is NearBlocks' count of public swaps; swaps_all counts every route, from NEAR's dashboard, and is empty after
# the dashboard's last reading.
intents_daily = columns(f"""
  select i.date_day d, i.volume_usd vol,
         case when not i.is_fee_revenue_provisional then i.fees_usd end fees,
         case when not i.is_fee_revenue_provisional then i.revenue_usd end rev,
         i.public_swaps swaps, i.confidential_tvl_usd conf_tvl, i.public_volume_usd pub,
         s.swaps swaps_all
  from gold.fct_intents_daily i left join gold.fct_dune_intents_swaps_daily s using (date_day)
  where i.date_day <= {LAST} order by 1""", 0)

intents_weekly = columns(f"""
  select date_trunc('week', date_day) d, sum(volume_usd) vol, sum(fees_usd) fees,
         sum(revenue_usd) rev, sum(public_swaps) swaps, sum(public_volume_usd) pub
  from gold.fct_intents_daily where date_day <= {FEES} and {full_week(FEES)} group by 1 order by 1""", 0)

revenue_monthly = table(f"""
  select date_trunc('month', date_day) m, account_id, sum(received_usd) usd
  from gold.fct_revenue_inflows_daily
  where date_trunc('month', date_day) + interval 1 month - interval 1 day <= {LAST}
  group by 1, 2 order by 1, 2""", 0)

peers = table(f"""
  select chain_id,
         last(market_cap_usd order by date_day) mcap,
         last(tvl_usd order by date_day) tvl,
         last(stablecoins_usd order by date_day) stablecoins,
         last(market_cap_basis order by date_day) mcap_basis,
         sum(fees_usd) filter (where {F30}) fees_30d,
         sum(revenue_usd) filter (where {F30}) revenue_30d,
         sum(dex_volume_usd) filter (where {F30}) dex_30d
  from gold.fct_peer_daily group by 1 order by mcap desc nulls last, chain_id""", 2)

peer_fees_weekly = {}
for chain in [p["chain_id"] for p in peers]:
    peer_fees_weekly[chain] = columns(f"""
      select date_trunc('week', date_day) d, sum(fees_usd) fees
      from gold.fct_peer_daily
      where chain_id = '{chain}' and {whole_weeks(FEES, 730)}
      group by 1 order by 1""", 0)

recon = table("""
  select check_id, metric, subject, source_a, value_a, source_b, value_b, diff_pct, tolerance_pct,
         independence, status, explanation, gap_kind
  from gold.dq_reconciliation
  order by case status when 'differs' then 0 else 1 end, diff_pct desc, check_id, subject""", 4)

# What an outsider can still count, for the month in progress and the month before it. NearBlocks reads the public
# chain, so it sees public routes only; the Explorer lists 1Click's swaps, public or confidential.
outside_counts = table(f"""
  select cast(date_trunc('month', d.date_day) as date) m, count(*) as n_days,
         avg(d.public_swaps) swaps, avg(d.public_accounts) accounts, avg(o.senders) senders,
         sum(least(d.public_volume_usd, d.volume_usd)) / sum(d.volume_usd) public_part
  from gold.fct_intents_daily d left join gold.fct_intents_1click_daily o using (date_day)
  where d.date_day <= {LAST} and d.date_day >= date_trunc('month', {LAST} - interval 1 month)
  group by 1 order by 1""", 4)

# "confidential intents" in NEAR's list is a way of settling, not a channel, so it is left out of the ranking and
# the shares are of the fees that name a channel. Its amount is published beside the ranking.
channels = table("""
  select referral, fees_usd, fees_usd / sum(fees_usd) over () as share
  from gold.fct_intents_fee_channels
  where snapshot_date = (select max(snapshot_date) from gold.fct_intents_fee_channels)
    and referral <> 'confidential intents'
  order by fees_usd desc, referral limit 8""")
channel_bucket = table("""
  select fees_usd from gold.fct_intents_fee_channels
  where snapshot_date = (select max(snapshot_date) from gold.fct_intents_fee_channels)
    and referral = 'confidential intents'""")

# All-route volume by blockchain over the 30 days the last Dune reading covers, as NEAR's dashboard splits it
dune_chains_30d = table(f"""
  select blockchain, sum(volume_usd) vol from gold.fct_dune_intents_chain_daily
  where {U30} group by 1 having sum(volume_usd) > 0 order by 2 desc, 1""", 0)
# Swaps across all routes, which only NEAR's dashboard counts, and the day that count runs to
dune_swaps_all = one("select max(date_day) as through, sum(swaps) as swaps from gold.fct_dune_intents_swaps_daily")

chains_30d = table(f"""
  select blockchain, sum(volume_usd) vol from gold.fct_intents_chain_daily
  where {U30} group by 1 order by 2 desc, 1 limit 10""", 0)

capture = table("""
  select mechanism, time_window, capture_rate from gold.fct_revenue_capture
  where snapshot_date = (select max(snapshot_date) from gold.fct_revenue_capture) order by 1, 2""")

gov = table("""
  select proposal_id, title, status, voters, turnout, for_venear, against_venear, voting_end_date
  from gold.fct_governance_proposals order by proposal_id desc""")

events = table("""
  select event_date, event_type, title, status from gold.dim_event order by event_date, title""")

# `gas` is the whole gas fee of the day, of which `burn` is the part that certainly burned. `signers` is
# fct_chain_daily.distinct_signers: accounts that signed, without those that only signed their own deletion. `never` is the NEAR in
# lockups whose owners never switched transfers on. The catalog says that column is understated before its last
# change, so it is exported only from the first day of its newest unbroken run at today's value.
NEVER_FROM = one("""
  with k as (select date_day, transfers_never_enabled_near as v from gold.fct_circulating_supply_daily),
       now as (select v from k order by date_day desc limit 1)
  select min(k.date_day) as d from k, now
  where k.date_day > (select coalesce(max(k2.date_day), date '1900-01-01') from k k2, now where abs(k2.v - now.v) >= 1)""")["d"]
daily = columns(f"""
  select date_day d, s.minted_near minted, s.burn_near burn, s.treasury_reward_near treasury,
         c.txns txns, m.price_usd price, s.total_supply_near supply, c.distinct_signers signers,
         c.active_accounts_with_relayed relayed, p.tvl_usd tvl,
         k.lockup_locked_near + k.foundation_locked_near as locked,
         c.gas_fee_near as gas,
         case when date_day >= date '{NEVER_FROM}' then k.transfers_never_enabled_near end as never
  from gold.fct_supply_daily s
  left join gold.fct_chain_daily c using (date_day)
  left join gold.fct_market_daily m using (date_day)
  left join (select date_day, tvl_usd from gold.fct_peer_daily where chain_id = 'near') p using (date_day)
  left join gold.fct_circulating_supply_daily k using (date_day)
  where date_day <= {LAST} order by 1""", 3)

assets30 = table(f"""
  select blockchain as chain, symbol, sum(volume_usd) vol
  from gold.fct_intents_asset_daily where {U30}
  group by 1, 2 having sum(volume_usd) > 0 order by 3 desc, 1, 2""", 0)

scopes = table("""
  select scope, metric, value_usd from gold.fct_intents_dashboard_readings
  where snapshot_date = (select max(snapshot_date) from gold.fct_intents_dashboard_readings) order by 1, 2""", 0)

validators_top = table("""
  select validator_account_id as account, stake_near as stake, stake_share as share, stake_rank as rank
  from gold.fct_validator_epoch
  where epoch_height = (select max(epoch_height) from gold.fct_validator_summary where is_epoch_complete)
  order by stake_rank, 1 limit 40""", 6)

stable_assets = table("""
  select symbol, circulating from gold.fct_stablecoin_assets
  where chain_id = 'near' and snapshot_date = (select max(snapshot_date) from gold.fct_stablecoin_assets)
  order by 2 desc, 1 limit 5""", 0)

conf_tvl_col = columns(f"""
  select date_day d, confidential_tvl_usd tvl from gold.fct_intents_daily
  where confidential_tvl_usd is not null and date_day <= {LAST} order by 1""", 0)

peer_weekly = {}
for chain in [p["chain_id"] for p in peers]:
    peer_weekly[chain] = columns(f"""
      select date_trunc('week', date_day) d, sum(fees_usd) fees, sum(revenue_usd) revenue,
             last(tvl_usd order by date_day) tvl, last(market_cap_usd order by date_day) mcap,
             sum(dex_volume_usd) dex, last(stablecoins_usd order by date_day) stablecoins
      from gold.fct_peer_daily
      where chain_id = '{chain}' and {whole_weeks(FEES, 735)}
      group by 1 order by 1""", 0)

wallet30 = table(f"""
  select account_id, sum(received_usd) usd from gold.fct_revenue_inflows_daily
  where {F30} group by 1 order by 2 desc, 1""", 0)

base30 = one(f"""
  select sum(minted_near) minted, sum(burn_near) burn, sum(treasury_reward_near) treasury
  from gold.fct_supply_daily where {D30}""")
intents30 = one(f"""
  select sum(volume_usd) vol, sum(fees_usd) fees, sum(revenue_usd) rev,
         sum(fees_usd) fees_page
  from gold.fct_intents_daily where {F30}""")
intents_all = one(f"""
  select sum(volume_usd) vol, sum(fees_usd) fees, sum(revenue_usd) rev,
         sum(public_swaps) swaps, count(*) as n_days
  from gold.fct_intents_daily where date_day <= {FEES}""")
intents_vol30 = one(f"select sum(volume_usd) v from gold.fct_intents_daily where {D30}")["v"]
# Volume and the public swap count do not change after their first reading, so their all-time totals run to the
# last full day; fees and revenue above stop at the settled day.
intents_all_last = one(f"select sum(volume_usd) vol, sum(public_swaps) swaps from gold.fct_intents_daily where date_day <= {LAST}")
price30 = one(f"select avg(price_usd) p from gold.fct_market_daily where {D30}")
latest = one(f"""
  select s.total_supply_near supply, c.circulating_supply_near circulating, m.price_usd price, m.market_cap_usd mcap,
         m.fully_diluted_value_usd fdv
  from gold.fct_supply_daily s join gold.fct_market_daily m using (date_day)
  left join gold.fct_circulating_supply_daily c using (date_day)
  where date_day = {LAST}""")
chain30 = one(f"""
  select sum(txns) txns, avg(distinct_signers) active_v1, avg(active_accounts_with_relayed) active_v3
  from gold.fct_chain_daily where {D30}""")
# The newest complete epoch, as every chart of the validator set reads it: an epoch still in progress has not counted
# its blocks yet
validators = one("select * from gold.fct_validator_summary where is_epoch_complete order by epoch_height desc limit 1")
mpc = one("select participants, threshold from gold.fct_mpc_state order by snapshot_date desc limit 1")
venear = one("select total_venear, accounts from gold.fct_venear_snapshot order by snapshot_date desc limit 1")
config = one("select max_inflation_rate, protocol_reward_rate, gas_burn_rate from gold.fct_protocol_config order by snapshot_date desc limit 1")
gold_tables = one("select count(*) n from information_schema.tables where table_schema = 'gold'")["n"]
gold_columns = one("select count(*) n from information_schema.columns where table_schema = 'gold'")["n"]
sources = one("select count(distinct source) n from gold.dq_provenance")["n"]
recon_counts = one("""
  select count(*) total,
         count(*) filter (where status = 'agree') agree,
         count(*) filter (where status = 'differs') differs,
         count(*) filter (where status = 'agree' and independence = 'independent') independent_agree,
         count(*) filter (where status = 'agree' and independence <> 'independent') same_upstream_agree,
         count(*) filter (where status = 'differs' and independence = 'independent') independent_differs,
         count(*) filter (where status = 'differs' and independence <> 'independent') same_upstream_differs,
         count(*) filter (where status not in ('agree', 'differs')) not_available
  from gold.dq_reconciliation""")


# The Bitwise NEAR ETF: what traded per trading day, what reached the chain per UTC day, and the checks between them
etf_daily = columns("""
  select date_day d, nav_usd nav, market_price_usd price, premium_discount_pct prem, shares_outstanding shares,
         net_assets_usd assets, flow_shares, flow_usd flow, cumulative_flow_usd cum, flow_basis basis,
         reported_cumulative_usd rep_cum, near_in_trust, flow_near, reported_flow_usd rep_flow, staked_share staked
  from gold.fct_etf_nrr_daily order by 1""")
etf_chain = columns("""
  select c.date_day d, c.near_in_wallets near, c.running_settled_shares settled, c.rewards_near rewards,
         c.share_of_pool pool_share, c.share_of_circulating_supply circ, c.near_unstaking unstaking,
         c.wallets_in_pool wallets
  from gold.fct_etf_nrr_chain_daily c order by 1""", 6)
etf_checks = table("""
  select check_id, metric, source_a, value_a, source_b, value_b, diff_pct, independence, status
  from gold.dq_reconciliation where check_id like 'etf_%' order by check_id""")
etf_prices = one("""
  with e as (select min(date_day) filter (where flow_basis <> 'seed_capital') first_day, max(date_day) last_day
             from gold.fct_etf_nrr_daily)
  select e.first_day, e.last_day,
         (select price_usd from gold.fct_market_daily where date_day = e.first_day) first_price,
         (select price_usd from gold.fct_market_daily where date_day = e.last_day) last_price
  from e""")

# The thesis models. The scorecard is every claim in registry/claims.csv that the data can settle, with its
# measurement, its bar and how it stands; a claim supports the long case when a bull claim holds or a bear claim
# fails. The claims the data cannot settle are kept apart, so the front page lists only tested claims. The rest are
# the series behind the home page's figures and the subject pages that read the thesis tables.
claim_order = {r["claim_id"]: i for i, r in enumerate(csv.DictReader((ROOT / "registry" / "claims.csv").open()))}
all_claims = sorted(table("""
  select s.claim_id, s.side, c.pillar, c.reading, s.claim, s.value, s.comparison, s.threshold, c.unit, s.status, s.as_of_date,
         c.test, c.why_this_threshold why
  from gold.fct_thesis_scorecard s join gold.dim_claim c using (claim_id)""", 6), key=lambda r: claim_order[r["claim_id"]])
for row in all_claims:
    # not_testable and not_settled are both open: the data puts the claim on neither side
    row["stands"] = "open" if row["status"] not in ("holds", "fails") else "for" if (row["side"] == "bull") == (row["status"] == "holds") else "against"
scorecard = [r for r in all_claims if r["stands"] != "open"]
open_claims = [r for r in all_claims if r["stands"] == "open"]
tally = {k: sum(1 for r in all_claims if r["stands"] == k) for k in ("for", "against", "open")}

# `recv` and `burnt` are the two parts of `offs`: the NEAR the revenue wallets received and the NEAR burned, each
# over the NEAR minted in the same 30 days. Only the burned part leaves supply.
dilution = columns(f"""
  select date_day d, offset_share offs, gross_inflation_rate gross, net_inflation_rate net,
         nominal_staking_yield_rate nominal_yield, real_staking_yield_rate real_yield, staked_share staked,
         minted_30d_usd minted_usd, revenue_inflow_30d_usd revenue_usd,
         revenue_inflow_30d_near / nullif(minted_30d_near, 0) recv, burn_30d_near / nullif(minted_30d_near, 0) burnt
  from gold.fct_net_dilution_daily where date_day >= date '2025-01-01' and date_day <= {FEES} order by 1""", 5)
dilution_now = one(f"select * from gold.fct_net_dilution_daily where date_day = {FEES}")

scenarios = table("select * from gold.fct_deflation_scenarios order by scenario_id, capture_case", 6)

unit_economics = table("""
  select month_start m, is_month_complete complete, days_counted n_days, volume_usd vol, fees_usd fees, revenue_usd rev,
         fee_rate, capture_rate capture, net_take_rate take, confidential_volume_share confidential,
         revenue_log_change dlog, volume_log_effect vol_effect, fee_rate_log_effect fee_effect, capture_log_effect capture_effect
  from gold.fct_intents_unit_economics_monthly order by 1""", 6)

# 1Click channels by month: the eight that charged the most app fees over the complete months, and the rest as one
channel_months = table("""
  with top as (select referral from gold.fct_intents_channel_economics_monthly where is_month_complete
               group by 1 order by sum(app_fee_usd) desc, 1 limit 8)
  select month_start m, case when referral in (select referral from top) then referral else 'other' end referral,
         sum(app_fee_usd) fees, sum(volume_usd) vol, sum(finished_swaps) swaps, sum(refunded_swaps) refunded
  from gold.fct_intents_channel_economics_monthly where is_month_complete group by 1, 2 order by 1, 3 desc, 2""", 0)
channel_counts = columns("""
  select month_start m, count(*) channels, count(*) filter (where app_fee_usd >= 10000) paying_10k,
         sum(refunded_swaps) / nullif(sum(finished_swaps) + sum(refunded_swaps), 0) refunded_share
  from gold.fct_intents_channel_economics_monthly where is_month_complete group by 1 order by 1""", 4)

concentration = table("""
  select month_start m, dimension, is_month_complete complete, members, total_usd total, hhi, top_1_share top1,
         top_3_share top3, top_10_share top10, top_member, covered_share_of_volume covered
  from gold.fct_intents_concentration_monthly order by 2, 1""", 4)

# Market cap over a year of income, on each idea of income: the newest settled day, and month ends for two years
multiples_day = one("select max(date_day) d from gold.fct_valuation_multiples_daily where not is_provisional")["d"]
multiples_latest = table(f"""
  select chain_id, basis, basis_30d_usd, multiple, multiple * basis_30d_usd * 365 / 30 as market_cap_usd,
         days_with_value, multiple_365d
  from gold.fct_valuation_multiples_daily
  where date_day = date '{multiples_day}' order by 2, 1""", 4)
multiples_monthly = {}
for r in rows(f"""
  select chain_id, basis, date_trunc('month', date_day) m, last(multiple order by date_day) multiple
  from gold.fct_valuation_multiples_daily
  where not is_provisional and date_day > date '{multiples_day}' - interval 730 day
  group by 1, 2, 3 order by 1, 2, 3"""):
    series = multiples_monthly.setdefault(f"{r['chain_id']}|{r['basis']}", {"m": [], "v": []})
    series["m"].append(clean(r["m"]))
    series["v"].append(clean(r["multiple"], 2))

# ---- The Usage page ----
# Its event days come from dim_event, so a chart mark and the figures around it cannot drift apart.
def event_day(title):
    found = rows(f"select event_date as d from gold.dim_event where title ilike '{title}' order by event_date desc limit 1")
    if not found:
        sys.exit(f"registry/events.csv has no event titled like {title}")
    return found[0]["d"]


BREAK_DAY, RELAY_DAY = event_day("Kai-Ching claim stream%"), event_day("relay.tg stops%")
BREAK, RELAY = f"date '{BREAK_DAY}'", f"date '{RELAY_DAY}'"

# Day by day from the first day every layer exists. The five layers add up to all transactions (batch streams, HOT's
# game, the Sweat relayer, the Intents contract, everything else); `clean` is what is left without the batch streams.
# Callers are NearBlocks' count of the distinct accounts calling a contract. Swaps count every route, from NEAR's
# dashboard, and are empty after its last reading.
usage_days = columns(f"""
  select u.date_day as d, c.txns, u.batch_stream_txns as batch, u.hot_game_txns as hot, u.sweat_relayer_txns as sweat,
         u.intents_txns as intents, u.other_txns as other, u.txns_ex_batch_streams as clean,
         c.active_accounts_with_relayed as active, c.distinct_signers as signers,
         h.unique_callers as hot_callers, k.unique_callers as intents_callers, w.swaps
  from gold.fct_usage_quality_daily u
  join gold.fct_chain_daily c using (date_day)
  left join gold.fct_contract_daily h on h.date_day = u.date_day and h.account_id = 'game.hot.tg'
  left join gold.fct_contract_daily k on k.date_day = u.date_day and k.account_id = 'intents.near'
  left join gold.fct_dune_intents_swaps_daily w on w.date_day = u.date_day
  where u.other_txns is not null and u.date_day <= {LAST} order by 1""", 0)
for i, d in enumerate(usage_days["d"]):
    layers = sum(usage_days[k][i] for k in ("batch", "hot", "sweat", "intents", "other"))
    if layers != usage_days["txns"][i]:
        sys.exit(f"Usage layers on {d} add up to {layers}, but the day had {usage_days['txns'][i]} transactions")

# The break of 2 April 2026. The key migration's main run is the days it sent 100,000 transactions or more. Accounts
# outside the two streams are active accounts less those the Kai-Ching batch and the migration reached, read over
# three windows: the 22 days before the migration's main run, the days between the break and the stop of relay.tg,
# and 16 days after that stop.
migration = one(f"""
  select count(*) as n_days, min(date_day) as first_day, max(date_day) as last_day, sum(txns) as txns
  from gold.fct_contract_daily
  where account_id = 'sweat-migration.near' and txns >= 100000 and date_day between {BREAK} - 32 and {BREAK}""")
MIGRATION = f"date '{migration['first_day']}'"
usage_break = one(f"""
  with s as (
    select date_day,
           coalesce(max(unique_receivers) filter (where account_id = 'hotwallet.kaiching'), 0)
         + coalesce(max(unique_receivers) filter (where account_id = 'sweat-migration.near'), 0) as stream_accounts,
           max(unique_receivers) filter (where account_id = 'hotwallet.kaiching') as reach
    from gold.fct_contract_daily group by 1),
  d as (
    select c.date_day, c.txns, u.batch_stream_txns as batch, c.distinct_signers as signers,
           c.active_accounts_with_relayed - coalesce(s.stream_accounts, 0) as accounts, s.reach
    from gold.fct_chain_daily c left join gold.fct_usage_quality_daily u using (date_day) left join s using (date_day))
  select max(txns) filter (where date_day = {BREAK} - 1) as txns_before, max(txns) filter (where date_day = {BREAK}) as txns_on,
         max(batch) filter (where date_day = {BREAK} - 1) as batch_before, max(batch) filter (where date_day = {BREAK}) as batch_on,
         max(signers) filter (where date_day = {BREAK} - 1) as signers_before, max(signers) filter (where date_day = {BREAK}) as signers_on,
         median(reach) filter (where date_day < {BREAK} - 1) as reach,
         avg(accounts) filter (where date_day between {MIGRATION} - 22 and {MIGRATION} - 1) as accounts_before,
         avg(accounts) filter (where date_day between {BREAK} + 1 and {RELAY} - 2) as accounts_after,
         avg(accounts) filter (where date_day between {RELAY} + 2 and {RELAY} + 17) as accounts_later
  from d""")
day_of = lambda expr: clean(one(f"select cast({expr} as date) as d")["d"])
usage_break_out = {
    **{k: clean(v, 0) for k, v in usage_break.items()},
    "day": clean(BREAK_DAY), "relay_day": clean(RELAY_DAY),
    "migration_days": migration["n_days"], "migration_from": clean(migration["first_day"]), "migration_to": clean(migration["last_day"]),
    "before": [day_of(f"{MIGRATION} - 22"), day_of(f"{MIGRATION} - 1")],
    "after": [day_of(f"{BREAK} + 1"), day_of(f"{RELAY} - 2")],
    "later": [day_of(f"{RELAY} + 2"), day_of(f"{RELAY} + 17")],
}

# The busiest contracts the warehouse tracks: those above CONTRACT_FLOOR transactions a day. The page shows this
# query as it ran, so the text is sent with the rows.
CONTRACT_FLOOR = 15000
USAGE_CONTRACTS_SQL = f"""-- The busiest contracts the warehouse tracks, over the 30 days to {LAST_DAY}: transactions a day that touch the
-- account, their share of all transactions, the distinct accounts calling it a day, and the same transactions a
-- day in the 30 days that ended 180 days earlier. A transaction that touches two accounts counts under both, so
-- the rows do not add up. An account with three callers a day or fewer is a relayer when it reaches a thousand
-- accounts a day, and an oracle or bot when it does not.
with x as (
  select account_id, entity,
         sum(txns) filter (where date_day > {LAST} - 30) / 30.0 as txns_a_day,
         avg(unique_callers) filter (where date_day > {LAST} - 30) as callers_a_day,
         avg(unique_receivers) filter (where date_day > {LAST} - 30) as receivers_a_day,
         sum(txns) filter (where date_day <= {LAST} - 180 and date_day > {LAST} - 210) / 30.0 as txns_a_day_six_months_earlier
  from gold.fct_contract_daily
  where date_day <= {LAST}
  group by 1, 2
), t as (
  select avg(txns) as txns from gold.fct_chain_daily
  where date_day > {LAST} - 30 and date_day <= {LAST}
)
select x.account_id, x.entity, x.txns_a_day, x.txns_a_day / t.txns as share_of_all_txns, x.callers_a_day,
       case when x.callers_a_day <= 3 and x.receivers_a_day >= 1000 then 'relayer'
            when x.callers_a_day <= 3 then 'oracle or bot'
            else 'contract' end as kind,
       x.txns_a_day_six_months_earlier
from x cross join t
where x.txns_a_day >= {CONTRACT_FLOOR}
order by x.txns_a_day desc, x.account_id;"""
usage_contracts = table(USAGE_CONTRACTS_SQL.rstrip(";"), 4)

# Who the transactions are for, from the sample of blocks, where each transaction has one receiver and so counts
# once. Each day's shares are weighted by the chain's real count of transactions that day, because the sample's own
# daily total runs well above and below it. plus_minus is two standard errors with days as the clusters.
USAGE_FAMILIES_SQL = f"""-- Who NEAR's transactions are for, by month and over the 30 days to {LAST_DAY}, from the sample of blocks
-- (fct_receiver_sample_daily), in which each transaction has one receiver and so counts once. A receiver joins the
-- first family it fits. Each day's shares are weighted by the chain's real count of transactions that day.
-- plus_minus is two standard errors, with days as the clusters.
with sampled as (
  select date_day, txn_share,
         case when entity = 'Kai-Ching' or account_id like '%.kaiching' then 'Kai-Ching'
              when entity = 'HOT' then 'HOT contracts'
              when account_id like '%.tg' then 'HOT players'
              when entity = 'Sweat Economy' or account_id like '%.sweat' then 'Sweat'
              when entity is null and regexp_matches(account_id, '^[0-9a-f]{{64}}$') then 'Implicit accounts'
              when entity = 'NEAR Intents' or account_id like '%.omft.near' then 'NEAR Intents'
              when entity in ('Rhea', 'Intear', 'Meta Pool', 'LiNEAR', 'NEAR Protocol', 'Circle', 'Tether', 'Pyth') then 'DeFi and tokens'
              when entity in ('Omni Bridge', 'Rainbow Bridge', 'Aurora') or category = 'bridge' or account_id like '%.bridge.near' then 'Bridges'
              when entity = 'Chain Signatures' then 'Chain Signatures'
              else 'Everything else' end as family
  from gold.fct_receiver_sample_daily
  where date_day <= {LAST}
), families as (
  select distinct family from sampled
), days as (
  select 'month' as period, cast(date_trunc('month', c.date_day) as date) as period_start, c.date_day, c.txns
  from gold.fct_chain_daily c
  where c.date_day in (select date_day from sampled)
  union all
  select '30 days', cast({LAST} - 29 as date), c.date_day, c.txns
  from gold.fct_chain_daily c
  where c.date_day in (select date_day from sampled) and c.date_day > {LAST} - 30
), by_day as (
  select d.period, d.period_start, d.date_day, d.txns, f.family, coalesce(sum(s.txn_share), 0) * d.txns as family_txns
  from days d
  cross join families f
  left join sampled s on s.date_day = d.date_day and s.family = f.family
  group by 1, 2, 3, 4, 5
), with_hot as (
  select * from by_day
  union all
  select period, period_start, date_day, txns, 'HOT, contracts and players', sum(family_txns)
  from by_day where family in ('HOT contracts', 'HOT players')
  group by 1, 2, 3, 4
), totals as (
  select period, period_start, family, count(*) as days, sum(family_txns) / sum(txns) as share, sum(txns) as txns
  from with_hot group by 1, 2, 3
)
select t.period, t.period_start, t.family, t.days, t.share,
       2 * sqrt(t.days / greatest(t.days - 1.0, 1) * sum(power(w.family_txns - t.share * w.txns, 2))) / max(t.txns) as plus_minus
from totals t
join with_hot w using (period, period_start, family)
group by t.period, t.period_start, t.family, t.days, t.share
order by t.period desc, t.period_start, t.family;"""
usage_families = table(USAGE_FAMILIES_SQL.rstrip(";"), 5)
family_days = one(f"""
  select min(date_day) as first_day, max(date_day) as last_day, count(distinct date_day) as n_days,
         sum(sampled_txns) / count(distinct date_day) as sampled_a_day
  from gold.fct_receiver_sample_daily where date_day <= {LAST}""")

# The sample prompt's hypothesis, as the scorecard reads it (weeks cut on Mondays), with the lowest and highest
# value each cell takes when the same days are cut into weeks starting on the other six weekdays
usage_lags = table("""
  select leader, usage_measure, lead_weeks,
         max(correlation) filter (where week_shift_days = 0) as r,
         max(weeks) filter (where week_shift_days = 0) as weeks,
         max(chance_bound) filter (where week_shift_days = 0) as bound,
         min(correlation) as low, max(correlation) as high,
         max(first_week) filter (where week_shift_days = 0) as first_week,
         max(last_week) filter (where week_shift_days = 0) as last_week
  from gold.fct_usage_lead_correlations group by 1, 2, 3 order by 1, 2, 3""", 6)

# Gas paid a day in dollars beside the fees charged on Intents, over the same 30 settled days
usage_gas = one(f"""
  select avg(c.gas_fee_near * m.price_usd) as gas_usd, avg(i.fees_usd) as fees_usd
  from gold.fct_chain_daily c join gold.fct_market_daily m using (date_day) join gold.fct_intents_daily i using (date_day)
  where {F30}""")

usage = {
    "days": usage_days,
    "brk": usage_break_out,
    "contracts": usage_contracts,
    "contractsSql": USAGE_CONTRACTS_SQL,
    "contractFloor": CONTRACT_FLOOR,
    "families": usage_families,
    "familiesSql": USAGE_FAMILIES_SQL,
    "sample": {k: clean(v, 1) for k, v in family_days.items()},
    "lags": usage_lags,
    "gas": {k: clean(v, 0) for k, v in usage_gas.items()},
}

# Validator pools in the last complete epoch of each day, which is the epoch in force as the next day began: how many
# are seated and how many of them produced anything, how much of the stake the largest hold, the fewest pools that
# hold over a third and over two thirds of it, and the stake itself
validators_daily = columns("""
  with w as (select epoch_height,
                    count(*) filter (where coalesce(blocks_produced, 0) + coalesce(chunks_produced, 0)
                                           + coalesce(endorsements_produced, 0) > 0) as working
             from gold.fct_validator_epoch where is_epoch_complete group by 1)
  select s.approx_date_day as d, arg_max(s.validators, s.epoch_height) as validators,
         arg_max(s.top_10_share, s.epoch_height) as top10, arg_max(s.nakamoto_33, s.epoch_height) as nakamoto,
         arg_max(s.staking_ratio, s.epoch_height) as staked, arg_max(s.nakamoto_67, s.epoch_height) as two_thirds,
         arg_max(s.total_stake_near, s.epoch_height) as stake, arg_max(w.working, s.epoch_height) as working
  from gold.fct_validator_summary s left join w using (epoch_height)
  where s.is_epoch_complete and s.approx_date_day is not null
  group by 1 order by 1""", 4)

etf_absorption = columns("""
  select date_day d, cumulative_flow_near flow, cumulative_minted_near minted,
         cumulative_revenue_inflow_near revenue, cumulative_flow_to_issuance_ratio ratio,
         flow_30d_near flow30, minted_30d_near minted30, flow_to_issuance_30d_ratio ratio30
  from gold.fct_etf_absorption_daily order by 1""", 4)

# Intents against the market: its volume beside the DEX volume of the six peer chains, in complete months.
# It is a yardstick, not a market definition: those venues mostly trade within one chain.
market_share = columns(f"""
  with i as (select date_trunc('month', date_day) m, sum(volume_usd) intents from gold.fct_intents_daily group by 1),
       p as (select date_trunc('month', date_day) m, sum(dex_volume_usd) peers from gold.fct_peer_daily
             where chain_id <> 'near' group by 1)
  select i.m, i.intents, p.peers, i.intents / p.peers as ratio
  from i join p using (m)
  where i.m >= date '2025-01-01' and i.m + interval 1 month - interval 1 day <= {LAST}
  order by 1""", 6)

# What 1Click volume depends on. The month is the newest one the scorecard reads, and Bitcoin is counted by chain
# because its symbol changed from BTC to BTC(OMNI) during 2026.
ONECLICK_MONTH = one("select max(month_start) m from gold.fct_intents_channel_economics_monthly where is_month_complete")["m"]
# What each 1Click channel carried and charged in that month. A channel with under 1% of the month's volume is
# counted in one row, so the rows add up to the month.
channel_prices = table(f"""
  with in_month as (
    select referral, volume_usd, app_fee_usd, share_of_volume
    from gold.fct_intents_channel_economics_monthly
    where month_start = date '{ONECLICK_MONTH}')
  select case when share_of_volume >= 0.01 then referral else 'other' end as referral,
         count(*) as channels, sum(volume_usd) as vol, sum(app_fee_usd) as fees
  from in_month group by 1 order by 3 desc, 1""", 0)
# The part of that month's app fees paid straight to NEAR's revenue wallets
fees_to_near = one(f"""
  select sum(fee_usd) filter (where recipient in
             (select account_id from gold.dim_entity where entity = 'NEAR revenue wallets')) / sum(fee_usd) as part
  from gold.fct_intents_1click_fee_recipient_daily
  where is_in_daily_run and date_trunc('month', date_day) = date '{ONECLICK_MONTH}'""")["part"]
STABLES = "('USDT', 'USDC', 'DAI', 'USDT0', 'USDT0(DEPRECATED)', 'USDCx', 'xDAI', 'USDG', 'USD1', 'USDf', 'FRAX', 'EURe')"
oneclick_mix = columns(f"""
  select date_trunc('month', date_day) m, sum(amount_in_usd) vol,
         sum(amount_in_usd) filter (where origin_symbol = 'ZEC' or destination_symbol = 'ZEC') / sum(amount_in_usd) as zec,
         sum(amount_in_usd) filter (where origin_blockchain = 'btc' or destination_blockchain = 'btc') / sum(amount_in_usd) as btc,
         sum(amount_in_usd) filter (where origin_symbol in {STABLES} and destination_symbol in {STABLES}) / sum(amount_in_usd) as stables
  from gold.fct_intents_1click_pair_daily
  where is_in_daily_run and date_day >= date '2025-06-01' and date_trunc('month', date_day) <= date '{ONECLICK_MONTH}'
  group by 1 order by 1""", 6)
# All-route volume per day by asset group, from NEAR's dashboard. Stablecoins are the list the 1Click charts use.
# Bitcoin is the dashboard's BTC, which includes Bitcoin bridged to NEAR; wrapped Bitcoin on other chains stays in
# the remainder, which the page draws as other assets.
asset_groups_daily = columns(f"""
  select date_day d, sum(volume_usd) as vol,
         coalesce(sum(volume_usd) filter (where symbol in {STABLES}), 0) as stables,
         coalesce(sum(volume_usd) filter (where symbol = 'BTC'), 0) as btc,
         coalesce(sum(volume_usd) filter (where symbol = 'ZEC'), 0) as zec,
         coalesce(sum(volume_usd) filter (where symbol in ('ETH', 'WETH')), 0) as eth,
         coalesce(sum(volume_usd) filter (where symbol in ('NEAR', 'wNEAR')), 0) as near
  from gold.fct_dune_intents_asset_daily where date_day <= {LAST} group by 1 order by 1""", 0)
# Value held in NEAR Intents by day, from NEAR's dashboard: balances anyone can read on chain and those shielded on its
# private instance. From 2026 the dashboard also splits the value by asset; wrapped NEAR is carried in dollars and in
# NEAR at the day's price, beside the NEAR in the Bitwise fund's wallets.
intents_tvl_daily = columns(f"""
  with tvl as (
    select date_day, coalesce(sum(tvl_usd) filter (where scope = 'public'), 0) as pub,
           coalesce(sum(tvl_usd) filter (where scope = 'confidential'), 0) as conf
    from gold.fct_dune_intents_tvl_daily group by 1),
  wnear as (select date_day, tvl_usd as near_usd from gold.fct_dune_intents_tvl_asset_daily where symbol = 'wNEAR')
  select t.date_day d, t.pub, t.conf, w.near_usd, w.near_usd / p.price_usd as near, e.near_in_wallets as etf
  from tvl t left join wnear w using (date_day) left join gold.fct_market_daily p using (date_day)
  left join gold.fct_etf_nrr_chain_daily e using (date_day)
  where t.date_day <= {LAST} order by 1""", 0)
# DefiLlama's own row for NEAR Intents over the dashboard's public part, by month: the median of the days both hold.
# It says from which month DefiLlama's count can stand as a second source for the public pool, and how far off it was
# before then.
intents_row_monthly = table(f"""
  with pool as (select date_day, tvl_usd as pub from gold.fct_dune_intents_tvl_daily
                where scope = 'public' and tvl_usd > 0),
       llama as (select date_day, tvl_usd as listed from gold.fct_protocol_tvl_daily where protocol_slug = 'near-intents')
  select cast(date_trunc('month', p.date_day) as date) as m, count(*) as n, median(l.listed / p.pub) as part
  from pool p join llama l using (date_day)
  where p.date_day <= {LAST} group by 1 order by 1""")
# The largest assets in that value on the dashboard's last day
intents_tvl_assets = table(f"""
  select symbol, tvl_usd as usd, share_of_day as part from gold.fct_dune_intents_tvl_asset_daily
  where date_day = (select max(date_day) from gold.fct_dune_intents_tvl_asset_daily where date_day <= {LAST})
  order by tvl_usd desc limit 6""")
# Each swap's dollars count half on the asset sold and half on the asset bought, so the boxes add up to the month's volume
oneclick_sides = table(f"""
  with p as (select * from gold.fct_intents_1click_pair_daily
             where is_in_daily_run and date_trunc('month', date_day) = date '{ONECLICK_MONTH}'),
       sides as (select origin_blockchain as blockchain, origin_symbol as symbol, amount_in_usd as usd from p
                 union all
                 select destination_blockchain, destination_symbol, amount_in_usd from p)
  select coalesce(blockchain, 'unknown') as chain, coalesce(symbol, 'unknown') as symbol, sum(usd) / 2 as vol
  from sides group by 1, 2 having sum(usd) > 0 order by 3 desc, 1, 2""", 0)
# 1Click volume in that month from the chain a swap starts on to the chain it ends on. A chain with under 5% of the
# month's volume at both ends is counted in "other", so the rows add up to the month.
oneclick_corridors = table(f"""
  with p as (select coalesce(origin_blockchain, 'unknown') as o, coalesce(destination_blockchain, 'unknown') as d,
                    amount_in_usd as usd
             from gold.fct_intents_1click_pair_daily
             where is_in_daily_run and date_trunc('month', date_day) = date '{ONECLICK_MONTH}'),
       ends as (select o as c, sum(usd) as u from p group by 1 union all select d, sum(usd) from p group by 1),
       large as (select c from ends group by 1 having max(u) >= 0.05 * (select sum(usd) from p))
  select case when o in (select c from large) then o else 'other' end as o,
         case when d in (select c from large) then d else 'other' end as d, sum(usd) as vol
  from p group by 1, 2 having sum(usd) > 0 order by 3 desc, 1, 2""", 0)
# The part of it that starts and ends on one chain, counted before the small chains are grouped
corridor_same = one(f"""
  select sum(amount_in_usd) filter (where origin_blockchain = destination_blockchain) / sum(amount_in_usd) as part
  from gold.fct_intents_1click_pair_daily
  where is_in_daily_run and date_trunc('month', date_day) = date '{ONECLICK_MONTH}'""")["part"]
# The scorecard reads Zcash over the last three complete months together. The site's monthly series must add up to
# that figure, or the chart and the claim would show different numbers
zec_quarter = sum(z * v for z, v in zip(oneclick_mix["zec"][-3:], oneclick_mix["vol"][-3:])) / sum(oneclick_mix["vol"][-3:])
zec_scored = next(r["value"] for r in scorecard if r["claim_id"] == "zcash_is_on_a_fifth_of_volume")
if abs(zec_quarter - zec_scored) > 1e-4:
    sys.exit(f"1Click mix: Zcash is {zec_quarter} over the three months to {ONECLICK_MONTH}, but the scorecard has {zec_scored}")

# Six more questions: swap sizes, what the revenue wallets hold, locked NEAR, Chain Signatures, liquid staking
# and how fresh each dataset is.
size_month = table(f"""
  select size_band as band, sum(swaps) as swaps, sum(amount_in_usd) as usd
  from gold.fct_intents_1click_size_daily
  where is_in_daily_run and date_trunc('month', date_day) = date '{ONECLICK_MONTH}'
  group by 1 order by 1""", 0)
size_months = columns(f"""
  select date_trunc('month', date_day) as m,
         sum(swaps) filter (where size_band in ('10k_to_100k', '100k_and_over')) / sum(swaps) as swaps_10k,
         sum(amount_in_usd) filter (where size_band in ('10k_to_100k', '100k_and_over')) / sum(amount_in_usd) as usd_10k
  from gold.fct_intents_1click_size_daily
  where is_in_daily_run and date_day >= date '2025-06-01' and date_trunc('month', date_day) <= date '{ONECLICK_MONTH}'
  group by 1 order by 1""", 5)

# NEAR held at the end of each full week by the wallets that receive Intents revenue
wallet_rows = rows(f"""
  select date_trunc('week', date_day) as d, account_id, last(balance_near order by date_day) as held
  from gold.fct_wallet_balance_daily
  where account_id in (select distinct account_id from gold.fct_revenue_inflows_daily)
    and date_day >= (select min(date_day) from gold.fct_revenue_inflows_daily) and {full_week(LAST)}
  group by 1, 2 order by 1, 2""")
wallet_weeks = sorted({clean(r["d"]) for r in wallet_rows})
wallet_held = {"d": wallet_weeks, "accounts": {
    account: [next((clean(r["held"]) for r in wallet_rows if clean(r["d"]) == week and r["account_id"] == account), None) for week in wallet_weeks]
    for account in sorted({r["account_id"] for r in wallet_rows})}}

locked = columns(f"""
  select date_trunc('week', date_day) as d, last(lockup_locked_near order by date_day) as lockups,
         last(foundation_locked_near order by date_day) as foundation,
         last(circulating_share_of_total order by date_day) as circulating
  from gold.fct_circulating_supply_daily where {full_week(LAST)} group by 1 order by 1""", 4)

signer_weeks = columns(f"""
  select date_trunc('week', date_day) as d, avg(txns) as txns, avg(signers) as signers
  from gold.fct_chain_signatures_daily where {full_week(LAST)} group by 1 having count(*) = 7 order by 1""", 3)
signer_domains = table("""
  select snapshot_date as d, signature_domains as domains, domains_before as was
  from (select *, lag(signature_domains) over (order by snapshot_date) as domains_before from gold.fct_mpc_state)
  where domains_before is not null and domains_before <> signature_domains
    and snapshot_date >= (select min(date_day) from gold.fct_chain_signatures_daily)
  order by 1""")

# Liquid staking on the first day of each month, which is the one day every month has back to 2021, and on the newest day
lst_rows = rows("""
  select date_trunc('month', snapshot_date) as m, token, first(delegated_near order by snapshot_date) as staked
  from gold.fct_lst_snapshot group by 1, 2 order by 1, 2""")
lst_months_x = sorted({clean(r["m"]) for r in lst_rows})
lst_months = {"m": lst_months_x, "tokens": {
    token: [next((clean(r["staked"]) for r in lst_rows if clean(r["m"]) == month and r["token"] == token), None) for month in lst_months_x]
    for token in sorted({r["token"] for r in lst_rows})}}
lst_now = table("""
  select snapshot_date as d, token, delegated_near as staked from gold.fct_lst_snapshot
  where snapshot_date = (select max(snapshot_date) from gold.fct_lst_snapshot) order by 2""", 0)

freshness = table("""
  select dataset, model, cadence, latest_data_day, days_behind, max_days_behind, is_stale
  from gold.dq_freshness order by days_behind desc nulls last, dataset, model""")

# Day by day, for the charts that can be read by day, week or month. Each is the finest step its table holds;
# the page rolls it up, so the week and month views are sums, means or last readings of these same days.
def pivot(found, name, value, digits=4):
    """Rows of (d, name, value) as one list of days and one list of values per name, in step with the days."""
    days = sorted({clean(r["d"]) for r in found})
    at = {(clean(r["d"]), r[name]): clean(r[value], digits) for r in found}
    return {"d": days, "by": {key: [at.get((day, key)) for day in days] for key in sorted({r[name] for r in found})}}


market_daily = columns(f"""
  with p as (select date_day, sum(dex_volume_usd) as peers from gold.fct_peer_daily
             where chain_id <> 'near' group by 1)
  select i.date_day as d, i.volume_usd as intents, p.peers
  from gold.fct_intents_daily i join p using (date_day)
  where i.date_day >= date '2025-01-01' and i.date_day <= {FEES} order by 1""", 0)
oneclick_daily = columns(f"""
  with pairs as (
    select date_day, sum(amount_in_usd) as vol,
           sum(amount_in_usd) filter (where origin_symbol = 'ZEC' or destination_symbol = 'ZEC') as zec,
           sum(amount_in_usd) filter (where origin_blockchain = 'btc' or destination_blockchain = 'btc') as btc,
           sum(amount_in_usd) filter (where origin_symbol in {STABLES} and destination_symbol in {STABLES}) as stables
    from gold.fct_intents_1click_pair_daily where is_in_daily_run group by 1),
  sizes as (
    select date_day, sum(swaps) as swaps, sum(amount_in_usd) as usd,
           sum(swaps) filter (where size_band in ('10k_to_100k', '100k_and_over')) as swaps_10k,
           sum(amount_in_usd) filter (where size_band in ('10k_to_100k', '100k_and_over')) as usd_10k
    from gold.fct_intents_1click_size_daily where is_in_daily_run group by 1)
  select date_day as d, vol, coalesce(zec, 0) as zec, coalesce(btc, 0) as btc, coalesce(stables, 0) as stables,
         swaps, usd, coalesce(swaps_10k, 0) as swaps_10k, coalesce(usd_10k, 0) as usd_10k
  from pairs join sizes using (date_day)
  where date_day >= date '2025-06-01' and date_day <= {LAST} order by 1""", 0)
channel_daily = pivot(rows(f"""
  with top as (select referral from gold.fct_intents_channel_economics_monthly where is_month_complete
               group by 1 order by sum(app_fee_usd) desc, 1 limit 8)
  select date_day as d, case when referral in (select referral from top) then referral else 'other' end as referral,
         coalesce(sum(app_fee_usd) filter (where status = 'SUCCESS'), 0) as fees
  from gold.fct_intents_1click_channel_daily
  where is_in_daily_run and date_day >= date '2025-10-01' and date_day <= {LAST}
  group by 1, 2 order by 1, 2"""), "referral", "fees", 0)
# The days must add up to the months the scorecard reads, or the day view and the month view would disagree
for month in sorted({r["m"] for r in channel_months if r["m"] >= "2025-10-01"}):
    by_day = sum(v or 0 for values in channel_daily["by"].values() for d, v in zip(channel_daily["d"], values) if d[:7] == month[:7])
    by_month = sum(r["fees"] for r in channel_months if r["m"] == month)
    if abs(by_day - by_month) > max(50, 1e-4 * by_month):
        sys.exit(f"1Click channel fees for {month}: the days add up to {by_day}, the monthly table has {by_month}")
REVENUE_WALLETS = "(select distinct account_id from gold.fct_revenue_inflows_daily)"
inflow_daily = pivot(rows(f"""
  select date_day as d, account_id, sum(received_usd) as usd from gold.fct_revenue_inflows_daily
  where date_day <= {LAST} group by 1, 2 order by 1, 2"""), "account_id", "usd", 0)
wallet_daily = pivot(rows(f"""
  select date_day as d, account_id, balance_near as held from gold.fct_wallet_balance_daily
  where account_id in {REVENUE_WALLETS} and date_day <= {LAST}
    and date_day >= (select min(date_day) from gold.fct_revenue_inflows_daily)
  order by 1, 2"""), "account_id", "held", 0)
# What the Intents contract paid the revenue wallets, counted on the day it arrived: USDC at $1 and NEAR at the
# transfer's value. fct_revenue_inflows_daily counts NEAR only, so it books the months paid in USDC on the days the
# USDC was traded for NEAR. Every day from the first payment is listed, with a zero where nothing was paid.
USDC_ON_NEAR = "'nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1'"
RECEIVED = f"""
    select date_day, account_id, sum(case when asset_id = {USDC_ON_NEAR} then amount_token else amount_usd end) as usd,
           coalesce(sum(amount_token) filter (where asset_id = {USDC_ON_NEAR}), 0) as usdc
    from gold.fct_wallet_transfers
    where account_id in {REVENUE_WALLETS} and direction = 'in' and counterparty_id = 'intents.near'
      and asset_id in ('native:near', 'nep141:wrap.near', {USDC_ON_NEAR}) and date_day <= {LAST}
    group by 1, 2"""
RECEIVED_DAYS = f"""select date_day from gold.dim_date
    where date_day >= (select min(date_day) from paid) and date_day <= {LAST}"""
received_daily = pivot(rows(f"""
  with paid as ({RECEIVED}), days as ({RECEIVED_DAYS}), wallets as (select distinct account_id from paid)
  select d.date_day as d, w.account_id, coalesce(p.usd, 0) as usd
  from days d cross join wallets w left join paid p using (date_day, account_id)
  order by 1, 2"""), "account_id", "usd", 0)
received_usdc = columns(f"""
  with paid as ({RECEIVED}), days as ({RECEIVED_DAYS})
  select d.date_day as d, coalesce(sum(p.usdc), 0) as usdc
  from days d left join paid p using (date_day) group by 1 order by 1""", 0)
if received_usdc["d"] != received_daily["d"]:
    sys.exit("Revenue as received: the USDC days and the wallet days do not line up")
received_daily["usdc"] = received_usdc["usdc"]
# The two counts of revenue differ in when they book a dollar, not in how many there are. A renamed token or account
# would empty this series without an error, so stop if the totals drift apart.
received_total = sum(v or 0 for values in received_daily["by"].values() for v in values)
inflow_total = one(f"select sum(received_usd) v from gold.fct_revenue_inflows_daily where date_day <= {LAST}")["v"]
if abs(received_total / inflow_total - 1) > 0.03:
    sys.exit(f"Revenue as received adds up to {received_total:,.0f}, but the wallets' NEAR receipts to {inflow_total:,.0f}")

# NEAR's own monthly revenue, as revenue.near.org publishes it, to set beside what the wallets received
page_monthly = columns("""
  select month_start as m, revenue_usd as usd, revenue_near as near
  from gold.fct_revenue_page_monthly order by 1""", 0)

# NEAR received by the revenue wallets each day, the measure fct_net_dilution_daily adds up, beside its dollars
inflow_near_daily = columns(f"""
  select date_day as d, sum(received_near) as near, sum(received_usd) as usd
  from gold.fct_revenue_inflows_daily where date_day <= {LAST} group by 1 order by 1""", 0)

# 1Click app fees that name a revenue wallet as their recipient: the part of the revenue that has a public fee line
fee_lines_daily = pivot(rows(f"""
  select date_day as d, recipient as account_id, sum(fee_usd) as usd
  from gold.fct_intents_1click_fee_recipient_daily
  where is_in_daily_run and recipient in {REVENUE_WALLETS} and date_day <= {LAST}
  group by 1, 2 order by 1, 2"""), "account_id", "usd", 0)

# The few large movements of NEAR at the revenue wallets, to mark on the chart of what they hold: NEAR bought with
# USDC, NEAR moved from one revenue wallet to another, and NEAR sent out
wallet_events = table(f"""
  select date_day as d,
         case when counterparty_id = 'auroraliqsupport.near' then 'bought_with_usdc'
              when is_between_revenue_wallets then 'moved_between_wallets'
              else 'sent_out' end as event,
         account_id, sum(abs(amount_token)) as near
  from gold.fct_wallet_transfers
  where account_id in {REVENUE_WALLETS} and asset_id in ('native:near', 'nep141:wrap.near') and date_day <= {LAST}
    and ((direction = 'in' and counterparty_id = 'auroraliqsupport.near') or direction = 'out')
  group by 1, 2, 3 having sum(abs(amount_token)) >= 1000
  order by 1, 2, 3""", 0)

usage_daily = columns(f"""
  select date_day as d, txns_ex_batch_streams as ex_batch, txns_ex_batch_streams_and_sweat as ex_sweat
  from gold.fct_usage_quality_daily where date_day <= {LAST} order by 1""", 0)
signer_daily = columns(f"""
  select date_day as d, txns, signers from gold.fct_chain_signatures_daily where date_day <= {LAST} order by 1""", 0)
lst_daily = pivot(rows(f"""
  select snapshot_date as d, token, delegated_near as staked from gold.fct_lst_snapshot
  where snapshot_date >= date '2025-01-01' and snapshot_date <= {LAST} order by 1, 2"""), "token", "staked", 0)

# veNEAR locked and the accounts holding it, at the end of each week, for the Governance page's overview
venear_weeks = columns(f"""
  select date_trunc('week', snapshot_date) as d, last(total_venear order by snapshot_date) as total,
         last(accounts order by snapshot_date) as accounts
  from gold.fct_venear_snapshot where snapshot_date <= {LAST} group by 1 order by 1""", 0)

# ---- The Supply page ----
# Issuance as a yearly rate over 30 days, from the first window that lies wholly after issuance began, and the same
# after burn and buybacks. The second waits on what the revenue wallets received, so it stops at the settled day.
issuance_daily = columns(f"""
  select date_day as d, gross_inflation_rate as gross,
         case when date_day <= {FEES} then net_inflation_rate end as net
  from gold.fct_net_dilution_daily
  where gross_inflation_rate is not null and date_day <= {LAST}
    and date_day >= (select min(date_day) from gold.fct_supply_daily where minted_near > 0) + 29
  order by 1""", 6)

# The last 30-day window before issuance was halved, which ends the day before the event's date, at the precision of
# dilutionNow, so the page can split the fall since then into the cut's part and the part of burn and buybacks
before_cut = rows("""
  select n.date_day, n.gross_inflation_rate, n.net_inflation_rate, e.event_date as cut_day
  from gold.dim_event e join gold.fct_net_dilution_daily n on n.date_day = e.event_date - 1
  where e.title ilike 'Issuance halved%' order by e.event_date desc limit 1""")

# NEAR held by treasury.near at the end of each day, and every transfer of NEAR out of it, by day and receiver
treasury_daily = columns(f"""
  select date_day as d, balance_near as held from gold.fct_wallet_balance_daily
  where account_id = 'treasury.near' and date_day <= {LAST} order by 1""", 0)
treasury_out = table(f"""
  select date_day as d, counterparty_id as receiver, count(*) as transfers, sum(-amount_token) as near
  from gold.fct_wallet_transfers
  where account_id = 'treasury.near' and direction = 'out' and asset_id = 'native:near' and date_day <= {LAST}
  group by 1, 2 order by 1, 2""", 0)

# What staking pays, three ways, each scaled to a year the same way (growth over the window times 365 over its days):
# rewards over stake before pool fees (30 days), what the liquid staking tokens stNEAR and rNEAR paid (growth of NEAR
# per token over 90 days, weighted by the NEAR each has staked) and issuance (30 days). A liquid staking reading shows
# the first block of its day, so it is dated to the day before. LiNEAR is left out: its price stands still for days
# at a time. Daily readings begin on 2025-01-01 for stNEAR and later for rNEAR, so `tokens` says how many the rate
# rests on. The rates stop at the settled day, as the page's other 30-day figures do.
LST_PAID = """
    with p as (select snapshot_date as d, token, price_near, delegated_near from gold.fct_lst_snapshot
               where token in ('stNEAR', 'rNEAR') and snapshot_date >= date '2025-01-01')
    select a.d - 1 as date_day,
           sum((a.price_near / b.price_near - 1) * 365 / 90 * a.delegated_near) / sum(a.delegated_near) as liquid,
           count(*) as tokens
    from p a join p b on b.token = a.token and b.d = a.d - 90
    group by 1"""
yield_daily = columns(f"""
  with y as ({LST_PAID})
  select n.date_day as d, n.nominal_staking_yield_rate as before_fees, y.liquid, y.tokens, n.gross_inflation_rate as issuance
  from gold.fct_net_dilution_daily n left join y using (date_day)
  where n.nominal_staking_yield_rate is not null and n.date_day >= date '2025-01-01' and n.date_day <= {FEES}
  order by 1""", 6)
# Beside that rate: what the same two tokens grew by over the full 365 days, their share of all stake, the days
# this year on which LiNEAR's price did not move, and the net staking rate the Bitwise fund reports
staking_facts = one(f"""
  with p as (select snapshot_date as d, token, price_near, delegated_near from gold.fct_lst_snapshot
             where token in ('stNEAR', 'rNEAR')),
       y as (select sum((a.price_near / b.price_near - 1) * a.delegated_near) / sum(a.delegated_near) as year_growth,
                    sum(a.delegated_near) as staked
             from p a join p b on b.token = a.token and b.d = a.d - 365 where a.d = {FEES} + 1),
       st as (select avg(stake) as stake from (select approx_date_day as d, avg(total_stake_near) as stake
                                               from gold.fct_validator_summary group by 1)
              where d > {FEES} - interval 30 day and d <= {FEES}),
       li as (select count(*) filter (where price_near = before) as still, count(*) as days
              from (select snapshot_date, price_near, lag(price_near) over (order by snapshot_date) as before
                    from gold.fct_lst_snapshot where token = 'LiNEAR')
              where snapshot_date >= date_trunc('year', {FEES}) and snapshot_date <= {FEES} + 1),
       etf as (select net_staking_rate as rate, date_day as d from gold.fct_etf_nrr_daily
               where net_staking_rate is not null and date_day <= {LAST} order by date_day desc limit 1)
  select y.year_growth, y.staked / st.stake as share_of_stake, li.still as linear_still_days, li.days as linear_days,
         etf.rate as etf_rate, etf.d as etf_day
  from y, st, li, etf""")

# Stake by month, as the mean of each day's reading, in three parts: the Bitwise fund's wallets, the three pools
# named cnear and everything else. One sampled epoch moves by tens of millions when pools enter or leave the active
# set, so no finer step is exported.
stake_months = columns(f"""
  with st as (select approx_date_day as d, avg(total_stake_near) as stake from gold.fct_validator_summary
              where approx_date_day >= date '2025-01-01' and approx_date_day <= {LAST} group by 1),
       cn as (select s.approx_date_day as d, sum(v.stake_near) / count(distinct s.epoch_height) as cnear
              from gold.fct_validator_summary s join gold.fct_validator_epoch v using (epoch_height)
              where v.validator_account_id like 'cnear-%' group by 1),
       etf as (select date_day as d, near_in_wallets as etf from gold.fct_etf_nrr_chain_daily)
  select date_trunc('month', st.d) as m, avg(coalesce(etf.etf, 0)) as etf, avg(coalesce(cn.cnear, 0)) as cnear,
         avg(st.stake - coalesce(etf.etf, 0) - coalesce(cn.cnear, 0)) as other, count(*) as days
  from st left join etf using (d) left join cn using (d)
  group by 1 order by 1""", 0)

# Where the supply sits on the newest day, in parts that do not overlap. Staked is the mean of the last 30 days,
# because one sampled epoch leaves out pools that are outside the active set; its named parts are the newest
# readings. Exchange wallets are dollars across all assets over NEAR's price, so an upper bound. wNEAR is split by the
# registry's label for its holder. The page works out the unlabelled rest, so the parts add up to total supply.
WNEAR = "from gold.fct_token_holders where token_id = 'wrap.near' and snapshot_date = (select max(snapshot_date) from gold.fct_token_holders)"
supply_map = one(f"""
  select (select total_supply_near from gold.fct_supply_daily where date_day = {LAST}) as supply,
         (select avg(stake) from (select approx_date_day as d, avg(total_stake_near) as stake from gold.fct_validator_summary group by 1)
          where d > {LAST} - interval 30 day and d <= {LAST}) as staked,
         (select sum(delegated_near) from gold.fct_lst_snapshot
          where snapshot_date = (select max(snapshot_date) from gold.fct_lst_snapshot)) as lst,
         (select near_in_wallets from gold.fct_etf_nrr_chain_daily where date_day = {LAST}) as etf,
         (select sum(v.stake_near) from gold.fct_validator_epoch v where v.validator_account_id like 'cnear-%'
            and v.epoch_height = (select max(epoch_height) from gold.fct_validator_summary where is_epoch_complete)) as cnear,
         (select count(*) from gold.fct_validator_epoch v where v.validator_account_id like 'cnear-%'
            and v.epoch_height = (select max(epoch_height) from gold.fct_validator_summary where is_epoch_complete)) as cnear_pools,
         (select sum(e.balance_usd) / max(m.price_usd) from gold.fct_exchange_balance_daily e
          join gold.fct_market_daily m using (date_day) where e.date_day = {LAST}) as exchanges,
         (select sum(amount_token) {WNEAR} and holder_account_id = 'intents.near') as intents,
         (select sum(amount_token) {WNEAR} and holder_category = 'bridge') as bridges,
         (select sum(amount_token) {WNEAR} and holder_entity = 'Rhea') as rhea,
         (select sum(balance_near) from gold.fct_wallet_balance_daily
          where date_day = {LAST} and account_id in {REVENUE_WALLETS}) as revenue,
         (select balance_near from gold.fct_wallet_balance_daily where date_day = {LAST} and account_id = 'treasury.near') as treasury,
         (select max(snapshot_date) from gold.fct_token_holders) as holders_day""")
if any(v is None for v in supply_map.values()):
    sys.exit(f"The supply map lacks a part on {LAST_DAY}: {[k for k, v in supply_map.items() if v is None]}")
foundation_reading = one("""
  select reading_date as d, value as near from registry.near_supply_readings
  where reading = 'foundation_holding' order by reading_date desc limit 1""")

# ---- The Capital page ----
# One list of dollar-pegged tokens and one of bitcoin tokens, by the symbols NEAR's dashboard uses, shared by every
# Capital query on the site. NEAR in the pool is wNEAR and NEAR.
CAP_NEAR = "('wNEAR', 'NEAR')"
CAP_DOLLARS = "('USDC', 'USDT', 'USDT0', 'USDCX', 'DAI', 'USDG', 'USAD', 'FRAX', 'USD1', 'USDE', 'PYUSD', 'USDS', 'USDF')"
CAP_BITCOIN = "('BTC', 'NBTC', 'WBTC', 'CBBTC', 'XBTC', 'TBTC', 'LBTC')"
RHEA_CONTRACTS = "('contract.main.burrow.near', 'v2.ref-finance.near', 'dclv2.ref-labs.near')"
# DefiLlama's TVL for the NEAR chain by day, in dollars and counted in NEAR, with the days its reading of Rhea Lend
# halved and came back marked (fct_defi_tvl_daily). The page leaves those days empty.
cap_defi = columns(f"""
  select date_day as d, tvl_usd as usd, tvl_in_near as near, cast(is_fault as integer) as fault
  from gold.fct_defi_tvl_daily where date_day <= {LAST} order by 1""", 0)
# How closely the dollar figure follows NEAR's price: weekly changes of the median clean day over two years
cap_slope = one(f"""
  with w as (select date_trunc('week', date_day) as wk, median(tvl_usd) as v, median(near_price_day_before_usd) as p
             from gold.fct_defi_tvl_daily
             where not is_fault and date_day > {LAST} - interval 730 day and date_day <= {LAST} group by 1),
       r as (select ln(v / lag(v) over (order by wk)) as rv, ln(p / lag(p) over (order by wk)) as rp from w)
  select regr_slope(rv, rp) as slope, corr(rv, rp) as fit, count(rv) as weeks from r""")
# The value held in NEAR Intents by day, public and confidential together, and from 2026 its split by asset group.
# A day on which the dashboard gives no public value has no total. near_tokens is the pool's NEAR in dollars over NEAR's
# close that day.
cap_pool = columns(f"""
  with t as (select date_day, sum(tvl_usd) as total, count(tvl_usd) as parts, count(*) as scopes
             from gold.fct_dune_intents_tvl_daily group by 1),
       a as (select date_day,
                    coalesce(sum(tvl_usd) filter (where symbol in {CAP_NEAR}), 0) as near,
                    coalesce(sum(tvl_usd) filter (where upper(symbol) in {CAP_DOLLARS}), 0) as dollars,
                    coalesce(sum(tvl_usd) filter (where upper(symbol) in {CAP_BITCOIN}), 0) as bitcoin,
                    coalesce(sum(tvl_usd) filter (where symbol = 'ZEC'), 0) as zcash,
                    sum(tvl_usd) as assets
             from gold.fct_dune_intents_tvl_asset_daily group by 1)
  select t.date_day as d, case when t.parts = t.scopes then t.total end as total,
         a.near, a.dollars, a.bitcoin, a.zcash, a.assets - a.near - a.dollars - a.bitcoin - a.zcash as other,
         a.near / m.price_usd as near_tokens
  from t left join a using (date_day) left join gold.fct_market_daily m using (date_day)
  where t.date_day <= {LAST} order by 1""", 0)
# Stablecoins on NEAR as DefiLlama counts them, from the first day it reports
cap_stables = columns(f"""
  select date_day as d, stablecoins_usd as usd from gold.fct_peer_daily
  where chain_id = 'near' and stablecoins_usd is not null and date_day <= {LAST} order by 1""", 0)
# Who holds them: the top 100 holders of the four dollar tokens the warehouse reads, grouped. Only Rhea, Aurora and
# NEAR Intents carry a registry label; the Binance and bridge accounts are named from their account ids alone. The
# issuer's own treasury account is left out, because DefiLlama does not count what has not been issued.
CAP_HOLDERS = f"""
  with h as (
    select case when holder_account_id = 'binancecold3.near' then 'binancecold3.near'
                when holder_entity = 'Rhea' then 'Rhea lending and DEX'
                when holder_account_id = 'intents.near' then 'NEAR Intents'
                when holder_category = 'bridge'
                  or holder_account_id in ('mpc-multichain.near', 'multichainorg.near', 'omni.bridge.near', 'contract.portalbridge.near')
                  then 'Bridge accounts'
                else 'Other accounts in the top 100' end as holder,
           amount_token
    from gold.fct_token_holders
    where snapshot_date = (select max(snapshot_date) from gold.fct_token_holders)
      and symbol in ('USDT', 'USDC', 'USDT.e', 'USDC.e') and holder_account_id <> 'tether-treasury.near'),
  tot as (select sum(circulating) as usd from gold.fct_stablecoin_assets
          where chain_id = 'near' and snapshot_date = (select max(snapshot_date) from gold.fct_stablecoin_assets))
  select holder, sum(amount_token) as usd, sum(amount_token) / (select usd from tot) as part from h group by 1
  union all
  select 'Accounts below the top 100', (select usd from tot) - (select sum(amount_token) from h),
         1 - (select sum(amount_token) from h) / (select usd from tot)
  order by 2 desc, 1"""
cap_holders = table(CAP_HOLDERS, 4)
cap_holders_day = one("select max(snapshot_date) as d from gold.fct_token_holders")["d"]
# The value on NEAR counted once, on the newest day that DefiLlama's protocols, the dashboard's pool and the chain
# reads all have. The double count needs no price: for each staking token, the share of its supply that sits in
# Rhea's lending and DEX contracts, times DefiLlama's TVL for that token's protocol.
CAP_DAY = one("""select least((select max(date_day) from gold.fct_protocol_tvl_daily),
                              (select max(date_day) from gold.fct_dune_intents_tvl_daily),
                              (select max(snapshot_date) from gold.fct_wallet_holdings),
                              (select max(snapshot_date) from gold.fct_lst_snapshot)) as d""")["d"]
CAPD = f"date '{CAP_DAY}'"
CAP_TWICE = f"""
  select l.token, p.protocol_name, h.in_rhea / l.token_supply as part_in_rhea, p.tvl_usd,
         h.lend / l.token_supply * p.tvl_usd as in_lend_usd, (h.in_rhea - h.lend) / l.token_supply * p.tvl_usd as in_dex_usd,
         l.delegated_near, h.in_rhea / l.token_supply * l.delegated_near as in_rhea_near
  from gold.fct_lst_snapshot l
  join (select token_id, sum(amount_token) as in_rhea,
               coalesce(sum(amount_token) filter (where account_id = 'contract.main.burrow.near'), 0) as lend
        from gold.fct_wallet_holdings
        where snapshot_date = {CAPD} and account_id in {RHEA_CONTRACTS} group by 1) h on h.token_id = l.contract
  join gold.fct_protocol_tvl_daily p on p.date_day = {CAPD}
   and p.protocol_name = case l.token when 'stNEAR' then 'Meta Pool Near' when 'LiNEAR' then 'LiNEAR Protocol' when 'rNEAR' then 'RHEA LST' end
  where l.snapshot_date = {CAPD}
  order by 1"""
cap_twice = table(CAP_TWICE, 6)
if len(cap_twice) != 3:
    sys.exit(f"The staking tokens held in Rhea on {CAP_DAY} do not match DefiLlama's three liquid staking protocols: {cap_twice}")
cap_protocols = table(f"""
  select protocol_name as name, protocol_slug as slug, category, tvl_usd as tvl from gold.fct_protocol_tvl_daily
  where date_day = {CAPD} order by 4 desc, 1""", 0)
cap_pool_day = one(f"""
  select sum(tvl_usd) as total, sum(tvl_usd) filter (where scope = 'public') as pub,
         sum(tvl_usd) filter (where scope = 'confidential') as conf
  from gold.fct_dune_intents_tvl_daily where date_day = {CAPD}""")
# What the count leaves out, on the same day: the tokens the bridge contract holds for use on other chains, the
# exchange wallets DefiLlama labels, and DefiLlama's own figure for the chain
cap_left_out = one(f"""
  select (select sum(amount_token) from gold.fct_wallet_holdings
          where snapshot_date = {CAPD} and account_id = 'omni.bridge.near' and token_id = 'wrap.near') as bridge_wnear,
         (select sum(value_usd) from gold.fct_wallet_holdings
          where snapshot_date = {CAPD} and account_id = 'omni.bridge.near' and token_id = 'wrap.near') as bridge_wnear_usd,
         (select sum(amount_token) from gold.fct_wallet_holdings
          where snapshot_date = {CAPD} and account_id = 'omni.bridge.near' and token_id = 'zec.omft.near') as bridge_zec,
         (select sum(value_usd) from gold.fct_wallet_holdings
          where snapshot_date = {CAPD} and account_id = 'omni.bridge.near' and token_id = 'zec.omft.near') as bridge_zec_usd,
         (select sum(balance_usd) from gold.fct_exchange_balance_daily where date_day = {CAPD}) as exchanges_usd,
         (select count(*) from gold.fct_exchange_balance_daily where date_day = {CAPD} and balance_usd > 0) as exchanges,
         (select tvl_usd from gold.fct_peer_daily where chain_id = 'near' and date_day = {CAPD}) as defi_usd""")
# The check on chain: what the contract intents.near holds in tokens the warehouse can price, on the read that
# follows the dashboard's last day (a read shows the start of its day), against the dashboard's total for that day
cap_chain = one("""
  with h as (select sum(value_usd) as on_chain, count(*) filter (where value_usd is null) as unpriced,
                    count(*) filter (where value_usd is not null) as priced, max(snapshot_date) as read_day
             from gold.fct_wallet_holdings
             where account_id = 'intents.near'
               and snapshot_date = least((select max(snapshot_date) from gold.fct_wallet_holdings),
                                         (select max(date_day) + 1 from gold.fct_dune_intents_tvl_daily))),
       d as (select date_day, sum(tvl_usd) as total from gold.fct_dune_intents_tvl_daily
             where date_day = (select max(date_day) from gold.fct_dune_intents_tvl_daily) group by 1)
  select h.on_chain, h.unpriced, h.priced, h.read_day, d.total as dashboard, d.date_day as dashboard_day from h, d""")
# What Rhea's lending market and DEX hold on that day, in the tokens the warehouse can price: staking tokens, wrapped
# NEAR and everything else. Tokens are told apart by contract, not by the symbol a contract gives itself.
CAP_MADE = f"""
  select case when account_id = 'contract.main.burrow.near' then 'Rhea Lend' else 'Rhea DEX' end as place,
         coalesce(sum(value_usd) filter (where token_id in ('meta-pool.near', 'linear-protocol.near', 'lst.rhealab.near')), 0) as staked_usd,
         coalesce(sum(value_usd) filter (where token_id = 'wrap.near'), 0) as wnear_usd,
         sum(value_usd) as usd
  from gold.fct_wallet_holdings
  where snapshot_date = {CAPD} and account_id in {RHEA_CONTRACTS} and value_usd is not null
  group by 1
  order by 4 desc"""
cap_made = table(CAP_MADE, 0)
# What staying pays: the growth of NEAR per stNEAR between the first reads of two months, scaled to a year the plain
# way (growth times 365 over the days between them), as the site's other staking rates are. One point per complete month.
CAP_STNEAR = """
  with m as (
    select cast(date_trunc('month', snapshot_date) as date) as month, min(snapshot_date) as first_read,
           arg_min(price_near, snapshot_date) as near_per_token
    from gold.fct_lst_snapshot
    where token = 'stNEAR'
    group by 1
  )
  select a.month, (b.near_per_token / a.near_per_token - 1) * 365 / (b.first_read - a.first_read) as paid_a_year
  from m a
  join m b on b.month = cast(a.month + interval 1 month as date)
  where a.first_read = a.month and b.first_read = b.month
  order by 1"""
cap_stnear = columns(CAP_STNEAR, 5)
# How many times the pool turned over in each complete month: volume across all routes over the month's average pool,
# scaled to 30 days. A day with no total on the dashboard is left out of the average.
CAP_TURNS = f"""
  with pool as (
    select date_day, case when count(tvl_usd) = count(*) then sum(tvl_usd) end as pool_usd
    from gold.fct_dune_intents_tvl_daily
    group by 1
  ), months as (
    select cast(date_trunc('month', i.date_day) as date) as month, count(*) as days,
           sum(i.volume_usd) as volume_usd, avg(p.pool_usd) as average_pool_usd
    from gold.fct_intents_daily i
    join pool p using (date_day)
    where i.date_day <= {LAST}
    group by 1
  )
  select month, volume_usd, average_pool_usd, volume_usd / average_pool_usd / days * 30 as turns_per_30_days
  from months
  where days = day(last_day(month))
  order by 1"""
cap_turns = columns(CAP_TURNS, 3)
# Fees charged over the average value held, for the three protocols that charge nearly all application fees on NEAR:
# DefiLlama's fees for the year and for the 30 days to its newest read, over the mean value held across the same
# length of time to the dashboard's last day. Rhea Lend's mean leaves its fault days out.
CAP_FEES = """
  with last_day as (select max(date_day) as d from gold.fct_dune_intents_tvl_daily),
  held as (
    select 'near-intents' as protocol_slug, date_day, sum(tvl_usd) as usd
    from gold.fct_dune_intents_tvl_daily group by 2 having count(tvl_usd) = count(*)
    union all
    select 'rhea-dex', date_day, tvl_usd from gold.fct_protocol_tvl_daily where protocol_slug = 'rhea-dex'
    union all
    select 'rhea-lend', date_day, rhea_lend_tvl_usd from gold.fct_defi_tvl_daily
    where not is_fault and rhea_lend_tvl_usd is not null
  ), average as (
    select protocol_slug,
           avg(usd) filter (where date_day > d - 365) as held_year_usd,
           avg(usd) filter (where date_day > d - 30) as held_30d_usd
    from held, last_day
    where date_day <= d
    group by 1
  )
  select f.protocol_name, f.total_1y_usd as fees_year_usd, a.held_year_usd,
         f.total_1y_usd / a.held_year_usd as fees_over_held_year,
         f.total_30d_usd as fees_30d_usd, a.held_30d_usd,
         f.total_30d_usd * 365 / 30 / a.held_30d_usd as fees_over_held_30d_as_a_year
  from gold.fct_protocol_fees_snapshot f
  join average a using (protocol_slug)
  where f.snapshot_date = (select max(snapshot_date) from gold.fct_protocol_fees_snapshot) and f.measure = 'fees'
  order by 4 desc"""
cap_fees = table(CAP_FEES, 5)
cap_fee_share = one("""
  select sum(total_30d_usd) filter (where protocol_slug = 'near-intents')
           / sum(total_30d_usd) filter (where category <> 'Chain') as intents_30d,
         max(snapshot_date) as read_day
  from gold.fct_protocol_fees_snapshot
  where snapshot_date = (select max(snapshot_date) from gold.fct_protocol_fees_snapshot) and measure = 'fees'""")
dedent = lambda q: "\n".join(line[2:] if line.startswith("  ") else line for line in q.strip("\n").split("\n")) + ";"
capital = {
    "day": clean(CAP_DAY),
    "made": cap_made,
    "stnear": cap_stnear,
    "turns": cap_turns,
    "fees": cap_fees,
    "feeShare": {k: clean(v, 4) for k, v in cap_fee_share.items()},
    "defi": cap_defi,
    "slope": {k: clean(v, 4) for k, v in cap_slope.items()},
    "pool": cap_pool,
    "stables": cap_stables,
    "holders": cap_holders,
    "holdersDay": clean(cap_holders_day),
    "twice": cap_twice,
    "protocols": cap_protocols,
    "poolDay": {k: clean(v, 0) for k, v in cap_pool_day.items()},
    "leftOut": {k: clean(v, 0) for k, v in cap_left_out.items()},
    "chain": {k: clean(v, 0) for k, v in cap_chain.items()},
    "sql": {"near": CAP_NEAR, "dollars": CAP_DOLLARS, "bitcoin": CAP_BITCOIN, "rhea": RHEA_CONTRACTS,
            "holders": dedent(CAP_HOLDERS), "stnear": dedent(CAP_STNEAR),
            "turns": dedent(CAP_TURNS), "fees": dedent(CAP_FEES)},
}


# ---- The Developers page --------------------------------------------------------------------------------------------
# An author is a GitHub account with a commit on a repository's main branch in a week (an e-mail where the commit has
# no account), counted per repository, with bots not removed. So authors are never added across repositories here.
# Gold keeps old weeks from old reads, so every query is held to the newest 52 full weeks: "now" is the newest 26 of
# them and "before" the 26 before. The deployment periods are fixed days and are named where the page prints them.
DEV_LAST = one("select max(week_start) d from gold.fct_dev_activity_weekly")["d"]
DEV_52 = f"week_start > date '{DEV_LAST}' - interval 364 day"
DEV_NOW = f"week_start > date '{DEV_LAST}' - interval 182 day"
DEV_STEP, DEV_SUMMER, DEV_BASE, DEV_RECORD_MONTH = "2026-09-21", ("2026-06-23", "2026-09-20"), ("2025-10-28", "2026-04-30"), "2026-10-01"

dev_core = columns(f"""
  select week_start as d,
         max(authors_default_branch) filter (where repo = 'near/nearcore') as core,
         max(authors_default_branch) filter (where repo = 'near/mpc') as mpc
  from gold.fct_dev_activity_weekly
  where repo in ('near/nearcore', 'near/mpc') and {DEV_52}
  group by 1 order by 1""", 0)

# One repository for each chain, its main node software. Three ways to cut the year, so the page can say which
# directions hold on all of them, and four spans for the rank, which moves with the span.
dev_peers = table(f"""
  with w as (select *, {DEV_NOW} as is_now,
                    week_start > date '{DEV_LAST}' - interval 91 day as q4,
                    week_start > date '{DEV_LAST}' - interval 182 day and week_start <= date '{DEV_LAST}' - interval 91 day as q3,
                    week_start <= date '{DEV_LAST}' - interval 273 day as q1,
                    week_start > date '{DEV_LAST}' - interval 28 day as m1
             from gold.fct_dev_activity_weekly where repo_group = 'protocol' and {DEV_52})
  select ecosystem as chain, repo,
         avg(authors_default_branch) filter (where is_now) as now,
         avg(authors_default_branch) filter (where not is_now) as before,
         avg(authors_default_branch) filter (where is_now) / avg(authors_default_branch) filter (where not is_now) - 1 as change,
         avg(authors_default_branch) filter (where q4) / avg(authors_default_branch) filter (where q3) - 1 as change_13,
         avg(authors_default_branch) filter (where q4) / avg(authors_default_branch) filter (where q1) - 1 as change_first,
         avg(authors_default_branch) as a52, avg(authors_default_branch) filter (where q4) as a13,
         avg(authors_default_branch) filter (where m1) as a4
  from w group by 1, 2 order by 3 desc, 1""")

dev_repos = table(f"""
  select repo, avg(authors_default_branch) as authors, median(authors_default_branch) as typical,
         sum(commits_default_branch) as commits, min(week_start) filter (where commits_default_branch > 0) as first_week
  from gold.fct_dev_activity_weekly
  where ecosystem = 'near' and {DEV_52}
  group by 1 order by 2 desc, 4 desc, 1""")

# The first day whose first block carried each protocol version, for versions first seen inside the 52 weeks
dev_versions = table(f"""
  select protocol_version as version, min(date_day) as day
  from gold.dim_block_day where protocol_version is not null
  group by 1
  having min(date_day) between date '{DEV_LAST}' - interval 357 day and date '{DEV_LAST}' + interval 6 day
  order by 2""")

dev_deploys = columns(f"""
  select date_day as d, new_contracts_v3 as n from gold.fct_chain_daily
  where new_contracts_v3 is not null and date_day <= {LAST} order by 1""", 0)

# One standard error of the gap between two 26-week means of the core client's weekly authors, as a share of the
# mean, allowing for a week resembling the week before it
dev_noise = one(f"""
  with n as (select authors_default_branch a, lag(authors_default_branch) over (order by week_start) a1
             from gold.fct_dev_activity_weekly where repo = 'near/nearcore' and {DEV_52})
  select sqrt(2.0) * stddev_samp(a) / sqrt(26.0) * sqrt((1 + corr(a, a1)) / (1 - corr(a, a1))) / avg(a) as gap from n""")

dev_chain = one(f"""
  select avg(new_contracts_v3) filter (where {D30}) as last30,
         avg(new_contracts_v3) filter (where date_day between date '{DEV_SUMMER[0]}' and date '{DEV_SUMMER[1]}') as summer,
         avg(new_contracts_v3) filter (where date_day between date '{DEV_BASE[0]}' and date '{DEV_BASE[1]}') as base,
         avg(new_accounts) filter (where date_day >= date '{DEV_STEP}' - interval 28 day and date_day < date '{DEV_STEP}') as accounts_before,
         avg(new_accounts) filter (where date_day >= date '{DEV_STEP}' + interval 14 day) as accounts_after,
         sum(unique_contracts) filter (where date_day >= date '{DEV_STEP}' and new_contracts_v3 is not null)
           / sum(new_contracts_v3) filter (where date_day >= date '{DEV_STEP}' and unique_contracts is not null) as code_per_contract
  from gold.fct_chain_daily where date_day <= {LAST}""")

# NearBlocks' two older counts by full month: where one month stands on each
dev_record = one(f"""
  with m as (select date_trunc('month', date_day) as mth, sum(unique_contracts) as code, sum(new_contracts_v1) as new_v1
             from gold.fct_chain_daily group by 1
             having count(*) = day(last_day(min(date_day))) and count(unique_contracts) = count(*)),
       r as (select *, rank() over (order by code desc) as rank_code, rank() over (order by new_v1 desc) as rank_new,
                    count(*) over () as months from m)
  select code, new_v1, rank_code, rank_new, months from r where mth = date '{DEV_RECORD_MONTH}'""")

# App names first seen on 1Click from the day of the step, and how many of them made fewer than ten finished swaps
dev_names = one(f"""
  with n as (select referral, min(date_day) as first_day, coalesce(sum(swaps) filter (where status = 'SUCCESS'), 0) as finished
             from gold.fct_intents_1click_channel_daily
             where referral is not null and referral not in ('', '(none)') group by 1)
  select count(*) filter (where first_day >= date '{DEV_STEP}') as names,
         count(*) filter (where first_day >= date '{DEV_STEP}' and finished < 10) as small from n""")

developers = {
    "last": clean(DEV_LAST),
    "core": dev_core,
    "peers": dev_peers,
    "repos": dev_repos,
    "versions": dev_versions,
    "deploys": dev_deploys,
    "noise": clean(dev_noise["gap"]),
    "chain": {k: clean(v) for k, v in dev_chain.items()},
    "step": DEV_STEP,
    "summer": list(DEV_SUMMER),
    "base": list(DEV_BASE),
    "record": {"month": DEV_RECORD_MONTH, **{k: clean(v, 0) for k, v in dev_record.items()}},
    "names": {k: clean(v, 0) for k, v in dev_names.items()},
}


# ---- The Market page ------------------------------------------------------------------------------------------------
# NEAR beside six other chains. Prices are closes of the UTC day. A multiple is market cap over the income of the 30
# days to that day, as a year (gold.fct_valuation_multiples_daily), read on settled days only. "What reaches the token"
# is the gas burned at each day's close plus the dollars NEAR's three revenue wallets received. Prices, supply and
# market-cap ranks run to the newest full day; fees and multiples stop on the settled fee day.
# Each token's close on every day of the year to the newest day, one column per chain
mkt_prices = pivot(rows(f"""
  select date_day as d, chain_id, price_usd from gold.fct_peer_daily
  where date_day >= {LAST} - interval 365 day and date_day <= {LAST} and price_usd is not null
  order by 1, 2"""), "chain_id", "price_usd", 6)
for chain, closes in mkt_prices["by"].items():
    if closes[0] is None or closes[-1] is None:
        sys.exit(f"The Market page: {chain} has no close on the first or the last day of the year it draws")

# By settled day over a year: NEAR's multiple on app fees, the median of the six peers', NEAR's place among the chains
# that have a reading, its 30 days of app fees and its market cap, and its multiple on what reaches the token
mkt_multiples = columns(f"""
  with m as (select * from gold.fct_valuation_multiples_daily
             where not is_provisional and date_day > date '{multiples_day}' - interval 365 day),
       n as (select date_day, multiple as near, basis_30d_usd as fees_30d from m
             where chain_id = 'near' and basis = 'app_fees'),
       t as (select date_day, multiple as token from m where chain_id = 'near' and basis = 'holder_revenue'),
       p as (select m.date_day, median(m.multiple) as peer, count(m.multiple) as peers,
                    1 + count(*) filter (where m.multiple > n.near) as near_rank
             from m join n using (date_day)
             where m.chain_id <> 'near' and m.basis = 'app_fees' group by 1),
       c as (select date_day, market_cap_usd as cap from gold.fct_peer_daily where chain_id = 'near')
  select n.date_day as d, n.near, p.peer, p.peers, p.near_rank, n.fees_30d, c.cap, t.token
  from n join p using (date_day) join c using (date_day) left join t using (date_day)
  order by 1""", 4)

# By settled day, from the first day whose 90 days all lie after the revenue wallets' first receipt: market cap over
# a year of app fees and over a year of what reaches the token, each taken from the 90 days to that day
mkt_ninety = columns(f"""
  with inc as (
    select s.date_day, m.market_cap_usd as cap, p.fees_usd, coalesce(i.usd, 0) as wallets_usd,
           s.burn_near * m.price_usd + coalesce(i.usd, 0) as token_usd
    from gold.fct_supply_daily s
    join gold.fct_market_daily m using (date_day)
    left join (select date_day, sum(received_usd) as usd from gold.fct_revenue_inflows_daily group by 1) i using (date_day)
    left join (select date_day, fees_usd from gold.fct_peer_daily where chain_id = 'near') p using (date_day)
    where s.date_day <= {FEES}),
  w as (
    select date_day, cap, sum(fees_usd) over win as fees_90d, sum(token_usd) over win as token_90d,
           sum(wallets_usd) over win as wallets_90d, count(fees_usd) over win as fee_days, count(token_usd) over win as token_days,
           min(date_day) over win as first_day
    from inc window win as (order by date_day rows between 89 preceding and current row))
  select date_day as d, cap / (fees_90d * 365 / 90) as fees, cap / (token_90d * 365 / 90) as token,
         wallets_90d / fees_90d as wallets_over_fees
  from w
  where fee_days = 90 and token_days = 90 and first_day = date_day - interval 89 day
    and first_day >= (select min(date_day) from gold.fct_revenue_inflows_daily where received_usd > 0)
  order by 1""", 4)

# App fees by chain over the windows the page compares: the 90 days to the settled day against the same 90 days a
# year earlier (the scorecard's test) and against the 90 days before; the last three complete months against the
# three before; the last 30 days against the 30 before; the last 365 days. For NEAR, also the 90 days a year earlier
# moved on by 30 days, which is the base its yearly change will be measured against in a month.
MKT_Q_END = f"date_trunc('month', {FEES} + interval 1 day)"
mkt_quarters = one(f"""
  select {MKT_Q_END} - interval 6 month as before_from, {MKT_Q_END} - interval 3 month as now_from,
         {MKT_Q_END} - interval 1 day as now_to""")
mkt_growth = table(f"""
  select chain_id,
         sum(fees_usd) filter (where date_day > {FEES} - interval 90 day) as f90,
         sum(fees_usd) filter (where date_day > {FEES} - interval 455 day and date_day <= {FEES} - interval 365 day) as f90_year_ago,
         sum(fees_usd) filter (where date_day > {FEES} - interval 425 day and date_day <= {FEES} - interval 335 day) as f90_year_ago_in_a_month,
         sum(fees_usd) filter (where date_day > {FEES} - interval 180 day and date_day <= {FEES} - interval 90 day) as f90_before,
         sum(fees_usd) filter (where date_day > {FEES} - interval 30 day) as f30,
         sum(fees_usd) filter (where date_day > {FEES} - interval 60 day and date_day <= {FEES} - interval 30 day) as f30_before,
         sum(fees_usd) filter (where date_day > {FEES} - interval 365 day) as f365,
         sum(fees_usd) filter (where date_day >= {MKT_Q_END} - interval 3 month and date_day < {MKT_Q_END}) as q_now,
         sum(fees_usd) filter (where date_day >= {MKT_Q_END} - interval 6 month and date_day < {MKT_Q_END} - interval 3 month) as q_before,
         max(market_cap_usd) filter (where date_day = {FEES}) as cap,
         avg(market_cap_usd) filter (where date_day > {FEES} - interval 90 day) as cap_90d,
         avg(market_cap_usd) filter (where date_day > {FEES} - interval 455 day and date_day <= {FEES} - interval 365 day) as cap_90d_year_ago,
         count(gas_fees_usd) filter (where date_day > {FEES} - interval 30 day) as gas_days_30d
  from gold.fct_peer_daily where date_day <= {FEES} group by 1 order by 1""", 0)
mkt_claim = one("select value from gold.fct_thesis_scorecard where claim_id = 'near_fees_outgrew_the_median_peer'")["value"]
mkt_gap = (lambda g: g("near") - statistics.median(g(r["chain_id"]) for r in mkt_growth if r["chain_id"] != "near"))(
    lambda c: next(r["q_now"] / r["q_before"] - 1 for r in mkt_growth if r["chain_id"] == c))
if mkt_claim is not None and abs(mkt_gap - float(mkt_claim)) > 0.002:
    sys.exit(f"The Market page: fee growth here ({mkt_gap:.4f}) is not what the scorecard measures ({float(mkt_claim):.4f})")

# NEAR Intents over the same 30 settled days as the peers' flows, so the page can show NEAR without it
mkt_intents = one(f"""
  select sum(volume_usd) as volume_30d, sum(fees_usd) as fees_30d, sum(revenue_usd) as revenue_30d
  from gold.fct_intents_daily where {F30}""")

# The supply behind each market cap (market cap over price), on the newest day and a year earlier
mkt_supply = table(f"""
  select chain_id, max(implied_supply_tokens) filter (where date_day = {LAST}) as now,
         max(implied_supply_tokens) filter (where date_day = {LAST} - interval 365 day) as year_ago
  from gold.fct_peer_daily group by 1 order by 1""", 0)

# NEAR's place by market cap among the seven at the end of each month, and on the newest day
mkt_cap_rank = columns(f"""
  with ends as (select chain_id, date_trunc('month', date_day) as m, max(date_day) as d,
                       last(market_cap_usd order by date_day) as cap
                from gold.fct_peer_daily
                where market_cap_usd is not null and date_day <= {LAST} and date_day > {LAST} - interval 730 day
                group by 1, 2),
       ranked as (select m, d, chain_id, rank() over (partition by m order by cap desc) as place from ends)
  select d, place from ranked where chain_id = 'near' order by 1""", 0)

# Trading: NEAR's reported spot volume a day over the 30 days to the newest day, and the fund's net flow since launch
mkt_spot = one(f"""
  select avg(reported_spot_volume_usd) as volume_a_day, count(reported_spot_volume_usd) as days
  from gold.fct_market_daily where {D30}""")
mkt_fund = one(f"""
  select date_day as d, cumulative_flow_usd as flow from gold.fct_etf_nrr_daily
  where cumulative_flow_usd is not null and date_day <= {LAST} order by date_day desc limit 1""")

# What each market cap counts of its token's total supply, on the day the totals were read. TON has no reading.
mkt_supply_readings = table("""
  select chain_id, reading_date as d, total_supply_tokens as total, share_of_total_counted as share, read_from
  from gold.fct_peer_supply_readings
  where reading_date = (select max(reading_date) from gold.fct_peer_supply_readings)
  order by chain_id""", 6)

# The newest nightly reading of DefiLlama's fee lists that holds all seven chains, and the largest application on
# each chain in it by fees over its trailing 30 days
MKT_READ = one("""
  select max(snapshot_date) as d from (select snapshot_date from gold.fct_peer_app_fees_snapshot
                                       group by 1 having count(distinct chain_id) = 7)""")["d"]
mkt_apps = table(f"""
  select chain_id, protocol_name, category, fees_30d_usd as fees_30d, share_of_chain_fees_30d as share
  from gold.fct_peer_app_fees_snapshot
  where snapshot_date = date '{MKT_READ}'
  qualify row_number() over (partition by chain_id order by fees_30d_usd desc nulls last, protocol_name) = 1
  order by share desc, chain_id""", 6)

# NEAR's multiple on app fees over the median peer's, on every night's reading, with nothing left out and with three
# lists of DefiLlama's categories left out of every chain's fees. The categories are DefiLlama's; which to leave out
# is this page's own choice, so the page prints the range and scores nothing. Market cap is the day before the read.
MKT_YIELD_LISTS = [
    ("tokenised funds", ["RWA"]),
    ("tokenised funds and staked tokens", ["RWA", "Liquid Staking", "Liquid Restaking", "Restaking"]),
    ("those and yield products", ["RWA", "Liquid Staking", "Liquid Restaking", "Restaking",
                                  "Onchain Capital Allocator", "Yield", "Basis Trading"]),
]
mkt_listed = {r["category"] for r in rows(f"select distinct category from gold.fct_peer_app_fees_snapshot where snapshot_date = date '{MKT_READ}'")}
for name, categories in MKT_YIELD_LISTS:
    gone = [c for c in categories if c not in mkt_listed]
    if gone:
        sys.exit(f"The Market page: DefiLlama no longer lists the categories {gone}; the list '{name}' needs a look")
in_list = lambda categories: ", ".join(f"'{c}'" for c in categories)
mkt_yield = columns(f"""
  with sums as (
    select snapshot_date, chain_id, sum(fees_30d_usd) as all_fees,
           {", ".join(f"sum(fees_30d_usd) filter (where category not in ({in_list(c)})) as cut_{i}" for i, (_, c) in enumerate(MKT_YIELD_LISTS))}
    from gold.fct_peer_app_fees_snapshot where fees_30d_usd > 0 group by 1, 2),
  m as (
    select s.snapshot_date, s.chain_id, p.market_cap_usd / s.all_fees as m_all,
           {", ".join(f"p.market_cap_usd / s.cut_{i} as m_{i}" for i in range(len(MKT_YIELD_LISTS)))}
    from sums s join gold.fct_peer_daily p on p.chain_id = s.chain_id and p.date_day = s.snapshot_date - 1)
  select snapshot_date as d,
         max(m_all) filter (where chain_id = 'near') / median(m_all) filter (where chain_id <> 'near') as nothing_left_out,
         {", ".join(f"max(m_{i}) filter (where chain_id = 'near') / median(m_{i}) filter (where chain_id <> 'near') as cut_{i}" for i in range(len(MKT_YIELD_LISTS)))}
  from m group by 1 having count(*) = 7 order by 1""", 4)

# What each chain burns or keeps of its gas, by DefiLlama's nightly reading: the median of the six peers' market cap
# over a year of it, the same without the chains whose row the source rewrote between readings, and NEAR's on the
# burn read from the chain over the 30 days to the day before the reading
mkt_burn = columns("""
  with peers as (
    select snapshot_date, chain_id, multiple_on_chain_revenue as m, is_unstable
    from gold.fct_peer_chain_fees_snapshot where chain_id <> 'near' and multiple_on_chain_revenue is not null),
  near as (
    select d.snapshot_date,
           (select market_cap_usd from gold.fct_peer_daily where chain_id = 'near' and date_day = d.snapshot_date - 1)
           / ((select sum(s.burn_near * k.price_usd) from gold.fct_supply_daily s join gold.fct_market_daily k using (date_day)
               where s.date_day > d.snapshot_date - 31 and s.date_day <= d.snapshot_date - 1) * 365 / 30) as near_on_burn
    from (select distinct snapshot_date from peers) d)
  select p.snapshot_date as d, max(n.near_on_burn) as near, median(p.m) as peers,
         median(p.m) filter (where not p.is_unstable) as steady_peers
  from peers p join near n using (snapshot_date)
  group by 1 having count(*) = 6 order by 1""", 2)
mkt_unstable = table("""
  select chain_id, max(revenue_30d_highest_over_lowest) as spread from gold.fct_peer_chain_fees_snapshot
  where is_unstable group by 1 order by 1""", 2)

# Trading: reported spot volume over market cap, as a mean over the 30 days to each day, for NEAR and for the median
# of the peers whose volume covers every day the chart draws (TON's starts in June 2026)
MKT_TRADED = [r["chain_id"] for r in rows(f"""
  select chain_id from gold.fct_peer_daily
  where date_day > {LAST} - interval 394 day and date_day <= {LAST}
  group by 1 having count(reported_spot_volume_usd / market_cap_usd) = 394 order by 1""")]
if "near" not in MKT_TRADED or len(MKT_TRADED) < 4:
    sys.exit(f"The Market page: too few chains have a year of reported volume ({MKT_TRADED})")
mkt_turnover = columns(f"""
  with days as (
    select date_day, chain_id, avg(reported_spot_volume_usd / market_cap_usd) over w as turnover
    from gold.fct_peer_daily
    where chain_id in ({in_list(MKT_TRADED)}) and date_day > {LAST} - interval 394 day and date_day <= {LAST}
    window w as (partition by chain_id order by date_day range between interval 29 days preceding and current row))
  select date_day as d, max(turnover) filter (where chain_id = 'near') as near,
         median(turnover) filter (where chain_id <> 'near') as peer
  from days where date_day > {LAST} - interval 365 day
  group by 1 order by 1""", 6)


# Days marked on the price charts, each read from dim_event so a mark and the figures around it cannot drift apart
MKT_MARKS = [("Top Level Accounts%", "Top Level Accounts"), ("Tokenized stocks%", "Tokenised stocks"),
             ("Bitwise NEAR ETF launches%", "Bitwise ETF"), ("HSP-029 passes%", "HSP-029 passes")]

market = {
    "prices": mkt_prices,
    "multiples": mkt_multiples,
    "ninety": mkt_ninety,
    "growth": mkt_growth,
    "quarters": {k: clean(v) for k, v in mkt_quarters.items()},
    "intents": {k: clean(v, 0) for k, v in mkt_intents.items()},
    "supply": mkt_supply,
    "capRank": mkt_cap_rank,
    "spot": {k: clean(v, 0) for k, v in mkt_spot.items()},
    "fund": {k: clean(v, 0) for k, v in mkt_fund.items()},
    "marks": [{"d": clean(event_day(title)), "label": label} for title, label in MKT_MARKS],
    "fundDay": clean(event_day("Bitwise NEAR ETF launches%")),
    "rebateDay": clean(event_day("Developer gas rebate removed%")),
    "supplyReadings": mkt_supply_readings,
    "apps": {"read": clean(MKT_READ), "top": mkt_apps},
    "yieldCut": {**mkt_yield, "lists": [{"name": n, "categories": c} for n, c in MKT_YIELD_LISTS]},
    "burn": {**mkt_burn, "unstable": mkt_unstable},
    "turnover": {**mkt_turnover, "chains": MKT_TRADED},
}

# The ETF page. The fund's flow and the chain's issuance by calendar day from the Monday of its first trading week (the
# flow is zero on a day with no trading), its staking pool among validators by day, what else holds NEAR at its size, and the
# figures its readings print that are a query and not a point on a chart.
ETF_POOL = "bitwise_2.poolv1.near"
etf_days = columns("""
  with e as (select min(date_day) filter (where flow_basis <> 'seed_capital') first_day, max(date_day) last_day
             from gold.fct_etf_nrr_daily),
       i as (select date_day, sum(received_near) received from gold.fct_revenue_inflows_daily group by 1)
  select s.date_day d, coalesce(f.flow_near, 0) flow, s.minted_near minted, coalesce(i.received, 0) received
  from gold.fct_supply_daily s cross join e
  left join gold.fct_etf_nrr_daily f on f.date_day = s.date_day and f.flow_basis <> 'seed_capital'
  left join i on i.date_day = s.date_day
  where s.date_day between date_trunc('week', e.first_day) and e.last_day order by 1""", 2)
etf_pool = columns(f"""
  select v.approx_date_day d, arg_max(e.stake_rank, e.epoch_height) rank, arg_max(v.validators, e.epoch_height) validators,
         arg_max(v.total_stake_near, e.epoch_height) staked
  from gold.fct_validator_epoch e join gold.fct_validator_summary v using (epoch_height)
  where e.validator_account_id = '{ETF_POOL}' and v.is_epoch_complete and v.approx_date_day is not null
    and v.approx_date_day >= (select min(date_day) - 1 from gold.fct_etf_nrr_daily)
    and v.approx_date_day <= (select max(date_day) from gold.fct_etf_nrr_chain_daily)
  group by 1 order by 1""", 0)
etf_size = table(f"""
  with day as (select max(date_day) d from gold.fct_etf_nrr_chain_daily),
       bal as (select account_id, balance_near from gold.fct_wallet_balance_daily, day where date_day = day.d)
  select 'fund' as kind, 'The Bitwise ETF' as name, near_in_wallets as near
  from gold.fct_etf_nrr_chain_daily, day where date_day = day.d
  union all
  select 'lst', token, delegated_near from gold.fct_lst_snapshot
  where snapshot_date = (select max(snapshot_date) from gold.fct_lst_snapshot, day where snapshot_date <= day.d + 1)
  union all select 'revenue', 'NEAR''s revenue wallets', sum(balance_near) from bal where account_id in {REVENUE_WALLETS}
  union all select 'treasury', 'Protocol treasury', balance_near from bal where account_id = 'treasury.near'
  order by near desc, name""", 0)
etf_facts = one("""
  with d as (select * from gold.fct_etf_nrr_daily where flow_basis <> 'seed_capital'),
       e as (select min(date_day) first_day, max(date_day) last_day from d),
       seed as (select date_day, net_assets_usd, shares_outstanding from gold.fct_etf_nrr_daily where flow_basis = 'seed_capital'),
       dil as (select * from gold.fct_net_dilution_daily where date_day <= (select last_day from e) order by date_day desc limit 1),
       m as (select date_day, price_usd from gold.fct_market_daily),
       peers as (
         select chain_id,
                max(price_usd) filter (where date_day = (select last_day from e))
                  / max(price_usd) filter (where date_day = (select date_day from seed)) - 1 as since,
                max(price_usd) filter (where date_day = (select date_day from seed))
                  / max(price_usd) filter (where date_day = (select date_day - 29 from seed)) - 1 as before
         from gold.fct_peer_daily where chain_id <> 'near' group by 1),
       page as (select date_day, near_in_trust / shares_outstanding as nps from d
                where fund_page_shares is not null and near_in_trust is not null),
       c14 as (select * from gold.fct_etf_nrr_chain_daily order by date_day desc limit 14),
       -- A trading day whose flow was not taken from the chain: had the chain's count reached the fund's by the next one
       next as (select date_day, flow_shares, flow_basis, shares_outstanding,
                       lead(date_day) over (order by date_day) next_day from gold.fct_etf_nrr_daily),
       lag as (select n.date_day, c.running_settled_shares = n.shares_outstanding as caught_up
               from next n left join gold.fct_etf_nrr_chain_daily c on c.date_day = n.next_day
               where n.flow_basis not in ('chain_settlement', 'seed_capital') and n.flow_shares <> 0 and n.next_day is not null),
       year as (select arg_max(date_day, price_usd) d, max(price_usd) p from m, e
                where date_day >= date_trunc('year', e.last_day) and date_day <= e.last_day)
  select (select date_day from seed) seed_day, (select net_assets_usd from seed) seed_usd,
         (select shares_outstanding from seed) seed_shares,
         (select date_day from dil) rate_day, (select nominal_staking_yield_rate from dil) stake_rate,
         (select gross_inflation_rate from dil) supply_growth, (select real_staking_yield_rate from dil) real_rate,
         (select avg(rewards_near) * 365 / avg(near_in_wallets) from c14) chain_rate, (select count(*) from c14) chain_days,
         (select arg_max(net_staking_rate, date_day) from d where net_staking_rate is not null) net_rate,
         (select arg_max(gross_staking_rate, date_day) from d where gross_staking_rate is not null) gross_rate,
         (select arg_max(listed_wallets, date_day) from d where listed_wallets is not null) listed_wallets,
         (select (arg_max(nps, date_day) / arg_min(nps, date_day) - 1) * 365.0 / datediff('day', min(date_day), max(date_day)) from page) share_rate,
         (select min(date_day) from page) share_from, (select max(date_day) from page) share_to, (select count(*) from page) share_readings,
         (select price_usd from m where date_day = (select date_day from seed))
           / (select price_usd from m where date_day = (select date_day - 29 from seed)) - 1 near_before,
         (select price_usd from m where date_day = (select last_day from e))
           / (select price_usd from m where date_day = (select date_day from seed)) - 1 near_since,
         (select date_day - 29 from seed) before_day,
         (select min(before) from peers) peers_before_lo, (select max(before) from peers) peers_before_hi,
         (select max(since) from peers) peers_since_best, (select min(since) from peers) peers_since_worst,
         (select count(*) from peers) peers,
         (select p from year) year_high, (select d from year) year_high_day,
         (select price_usd from m where date_day = (select first_day from e)) first_close,
         (select count(*) filter (where caught_up) from lag) lag_caught, (select count(*) from lag) lag_days,
         (select min(nav_usd) from d where flow_shares > 0) lowest_creation_nav,
         (select arg_min(near_per_share, date_day) from d) nps_first, (select arg_max(near_per_share, date_day) from d) nps_last""")

# ---- The Governance page ---------------------------------------------------------------------------------------------
# Every real vote on vote.dao, oldest first: the contract's figures, and what each vote decides, which is read by hand
# from the proposal's own text and kept in registry/governance_decisions.csv. Six decimals at every size, because the
# veNEAR against HSP-029 is a dust amount and the page adds veNEAR up across votes. The end of a timelock keeps its
# hour, since nothing else on the page is that close.
gov_votes = [{k: round(float(v), 6) if isinstance(v, (float, Decimal)) else clean(v) for k, v in r.items()} for r in rows("""
  select proposal_id, hsp, short_name, kind, what_it_changes, title, status, voting_start_date as opened, voting_end_date as closed,
         voters, voters_for, voters_against, voters_abstain, snapshot_accounts, share_of_accounts_voting,
         support, approval_threshold, for_venear, against_venear, coalesce(abstain_venear, 0) as abstain_venear,
         eligible_venear, turnout, quorum_threshold, strftime(timelock_end_utc, '%Y-%m-%d %H:%M') as timelock_end,
         near_committed, usd_committed, ramp_months, grace_days, in_force_date, in_force_protocol_version
  from gold.fct_governance_decisions order by proposal_id""")]

# What the contract holds besides those votes, the day it was read, and the rate at which veNEAR grows by itself
gov_filings = one("""
  select count(*) as filed, count(*) filter (where is_test) as tests,
         count(*) filter (where not is_test and voters = 0) as never_opened,
         count(*) filter (where not is_test and voters > 0 and status = 'Defeated') as defeated,
         count(*) filter (where has_actions) as with_actions, max(read_on) as read_on,
         arg_max(venear_growth_per_year, proposal_id) filter (where venear_growth_per_year is not null) as growth_a_year
  from gold.fct_governance_proposals""")

# veNEAR outstanding and the accounts venear.dao has registered, by day from the first day there was any. A reading
# shows the first block of its day.
venear_daily = columns("""
  select snapshot_date as d, total_venear as total, accounts
  from gold.fct_venear_snapshot where total_venear > 0 order by 1""", 0)

# How much veNEAR rises in a day with no new account: the median over the newest 30 readings, and over the month of
# its peak. veNEAR grows at a fixed yearly rate on the NEAR locked, so that rise times 365 over the rate is an
# estimate of the NEAR locked.
venear_rise = one("""
  with v as (select snapshot_date, total_venear,
                    total_venear - lag(total_venear) over (order by snapshot_date) as rise,
                    accounts - lag(accounts) over (order by snapshot_date) as added
             from gold.fct_venear_snapshot),
       ends as (select max(snapshot_date) as last_day, arg_max(snapshot_date, total_venear) as peak_day from v)
  select (select median(rise) from v, ends where snapshot_date > last_day - 30 and added = 0) as now,
         (select median(rise) from v, ends
          where date_trunc('month', snapshot_date) = date_trunc('month', peak_day) and added = 0) as at_peak,
         (select peak_day from ends) as peak_day""")

# The day the first halved epoch reward was paid in 2025 (treasury.near receives a tenth of each epoch's issuance),
# the forum threads the warehouse follows, as last read, and the largest validator's stake in the last complete epoch
gov_cut_day = one("""
  with r as (select date_day, block_timestamp_ns,
                    amount_token / lag(amount_token) over (order by block_timestamp_ns) as against_the_one_before
             from gold.fct_wallet_transfers
             where account_id = 'treasury.near' and transfer_type = 'EpochRewards')
  select min(date_day) as d from r where against_the_one_before < 0.6""")["d"]
gov_threads = table("""
  select topic_id, title, created_date as created from gold.fct_governance_threads
  where snapshot_date = (select max(snapshot_date) from gold.fct_governance_threads) order by created_date, topic_id""")
gov_largest_stake = one("""
  select max(stake_near) as near from gold.fct_validator_epoch
  where epoch_height = (select max(epoch_height) from gold.fct_validator_summary where is_epoch_complete)""")["near"]

# The cap on issuance in the protocol config: as last read, as first read once the vote on the ramp had closed, and
# the rate the ramp ends at (registry/issuance_scenarios.csv). And the share of gas contracts received before the
# protocol version that removed it.
gov_cap = one("""
  select (select arg_max(max_inflation_rate, snapshot_date) from gold.fct_protocol_config) as now,
         (select max(snapshot_date) from gold.fct_protocol_config) as read_on,
         (select arg_min(c.max_inflation_rate, c.snapshot_date) from gold.fct_protocol_config c
          where c.snapshot_date >= (select min(voting_end_date) from gold.fct_governance_decisions
                                    where ramp_months is not null)) as when_voted,
         (select annual_issuance_rate from registry.issuance_scenarios where scenario_id = 'hsp029_end_state') as target,
         (select u.contract_gas_reward_rate_before from registry.protocol_upgrades u
          join gold.fct_governance_decisions d on d.in_force_protocol_version = u.protocol_version) as rebate_share_before""")

governance = {
    "votes": gov_votes,
    "filings": {k: clean(v, 6) for k, v in gov_filings.items()},
    "venearDaily": venear_daily,
    "rise": {"now": round(float(venear_rise["now"]), 2), "atPeak": round(float(venear_rise["at_peak"]), 2),
             "peakDay": clean(venear_rise["peak_day"])},
    "cap": {k: clean(v, 6) for k, v in gov_cap.items()},
    "cutDay": clean(gov_cut_day),
    "threads": gov_threads,
    "largestStake": clean(gov_largest_stake, 0),
}

# ---- The Security page -----------------------------------------------------------------------------------------------
# Every figure of the validator set is read in the last complete epoch of a day, the epoch in force as the next day
# began, which is the rule the daily series above follows. "Now" is the newest of those epochs. The warehouse reads
# about one epoch in three. A pool is a staking pool account with a seat in an epoch; nothing here says who runs it.
SEC = """
  d as (select approx_date_day as d, max(epoch_height) as ep, arg_max(validators, epoch_height) as pools,
               arg_max(total_stake_near, epoch_height) as stake, arg_max(nakamoto_33, epoch_height) as third
        from gold.fct_validator_summary where is_epoch_complete and approx_date_day is not null group by 1),
  a as (select max(d) as d1, arg_max(ep, d) as e1 from d),
  e1 as (select e.* from gold.fct_validator_epoch e, a where e.epoch_height = a.e1),
  w as (select epoch_height, count(*) as seated,
               count(*) filter (where coalesce(blocks_produced, 0) + coalesce(chunks_produced, 0)
                                      + coalesce(endorsements_produced, 0) > 0) as working,
               sum(blocks_produced)::double / sum(blocks_expected) as block_rate,
               coalesce(sum(stake_share) filter (where endorsements_produced::double
                                                       / nullif(endorsements_expected, 0) < 0.7), 0) as stake_failing
        from gold.fct_validator_epoch where is_epoch_complete group by 1),
  wd as (select s.approx_date_day as d, w.* from w join gold.fct_validator_summary s using (epoch_height)
         where s.approx_date_day is not null)"""

# The newest complete epoch: the pools that together first pass a third of the stake, the pools that produce blocks,
# the work done, and the three pools named cnear. Pools that share a name are counted once under two rules, a narrow
# one (figment, cnear, bitwise) and a wide one that adds svrn: a reading of account names, not of who runs a pool.
sec_now = one(f"""
  with {SEC},
  grp as (select stake_share,
                 case when validator_account_id like '%figment%' then 'figment'
                      when validator_account_id like 'cnear-%' then 'cnear'
                      when validator_account_id in ('bitwise_1.poolv1.near', 'bitwise_2.poolv1.near') then 'bitwise'
                      else validator_account_id end as narrow,
                 case when validator_account_id like '%figment%' then 'figment'
                      when validator_account_id like 'cnear-%' then 'cnear'
                      when validator_account_id like 'svrn%' then 'svrn'
                      when validator_account_id in ('bitwise_1.poolv1.near', 'bitwise_2.poolv1.near') then 'bitwise'
                      else validator_account_id end as wide
          from e1),
  gn as (select sum(sh) over (order by sh desc, g) as run, row_number() over (order by sh desc, g) as rk
         from (select narrow as g, sum(stake_share) as sh from grp group by 1)),
  gw as (select sum(sh) over (order by sh desc, g) as run, row_number() over (order by sh desc, g) as rk
         from (select wide as g, sum(stake_share) as sh from grp group by 1)),
  worst as (select epoch_height, d, block_rate from wd order by block_rate, epoch_height limit 1),
  firsts as (select validator_account_id, min(epoch_height) as first_ep from gold.fct_validator_epoch group by 1),
  silent as (select e.stake_share, f.first_ep = e.epoch_height as is_new
             from gold.fct_validator_epoch e join firsts f using (validator_account_id), worst
             where e.epoch_height = worst.epoch_height and e.blocks_expected > 0 and e.blocks_produced = 0)
  select a.e1 as epoch, a.d1 as day, (select count(*) from e1) as pools, (select sum(stake_near) from e1) as stake,
         (select third from d, a where d = d1) as third,
         (select sum(stake_share) from e1 where stake_rank <= (select third from d, a where d = d1)) as third_share,
         (select sum(stake_near) from e1 where stake_rank <= (select third from d, a where d = d1)) as third_stake,
         (select arg_max(price_usd, date_day) from gold.fct_market_daily, a where date_day <= d1) as price,
         (select count(*) from e1 where blocks_expected > 0) as producers,
         (select sum(stake_share) from e1 where blocks_expected > 0) as producers_share,
         (select count(*) from e1 where stake_rank > 40) as rest_pools,
         (select sum(stake_share) from e1 where stake_rank > 40) as rest_share,
         (select min(rk) from gn where run > 1.0 / 3) as groups_narrow,
         (select min(rk) from gw where run > 1.0 / 3) as groups_wide,
         (select block_rate from w, a where epoch_height = e1) as block_rate,
         (select seated - working from w, a where epoch_height = e1) as idle,
         (select d from worst) as worst_day, (select block_rate from worst) as worst_rate,
         (select count(*) from silent) as worst_silent, (select sum(stake_share) from silent) as worst_silent_share,
         (select count(*) filter (where is_new) from silent) as worst_silent_new,
         (select max(stake_failing) from w) as most_failing, (select arg_max(d, stake_failing) from wd) as most_failing_day,
         (select count(*) from gold.fct_validator_summary) as epochs_on_file,
         (select max(epoch_height) - min(epoch_height) + 1 from gold.fct_validator_summary) as epochs_in_span,
         (select count(*) from e1 where validator_account_id like 'cnear-%') as cnear_pools,
         (select sum(stake_share) from e1 where validator_account_id like 'cnear-%') as cnear_share,
         (select min(s.approx_date_day) from gold.fct_validator_epoch e join gold.fct_validator_summary s using (epoch_height)
          where e.validator_account_id like 'cnear-%') as cnear_first_day
  from a""")
# Seats in the other complete epochs of the newest day: offline pools are dropped for an epoch and seated again
sec_other_epochs = [r["validators"] for r in rows(f"""
  with {SEC}
  select s.validators from gold.fct_validator_summary s, a
  where s.is_epoch_complete and s.approx_date_day = a.d1 and s.epoch_height <> a.e1 order by s.epoch_height""")]

# The pools that left: seated 60 days before the newest day, and in no complete epoch of the newest day. Their stake is
# as it was when the 60 days began. The fall is split at one protocol upgrade, the version the registry dates to its
# first block, and each pool's work is read in the last epoch it was seated. The band is a size many small pools share.
SEC_UPGRADE = 87
sec_leavers = one(f"""
  with {SEC},
  up as (select cast(first_block_utc as date) as day from registry.protocol_upgrades where protocol_version = {SEC_UPGRADE}),
  base as (select e.* from gold.fct_validator_epoch e, a where e.epoch_height = (select ep from d where d = a.d1 - 60)),
  newest as (select distinct e.validator_account_id
             from gold.fct_validator_epoch e join gold.fct_validator_summary s using (epoch_height), a
             where s.is_epoch_complete and s.approx_date_day = a.d1),
  gone as (select b.* from base b where b.validator_account_id not in (select validator_account_id from newest)),
  last_seen as (select g.validator_account_id, max(s.approx_date_day) as day,
                       arg_max(e.stake_near, e.epoch_height) as stake,
                       arg_max(e.endorsements_produced::double / nullif(e.endorsements_expected, 0), e.epoch_height) as rate
                from gone g join gold.fct_validator_epoch e using (validator_account_id)
                join gold.fct_validator_summary s on s.epoch_height = e.epoch_height
                where s.is_epoch_complete and s.approx_date_day is not null group by 1),
  band as (select dd.d, count(*) filter (where e.stake_near between 40000 and 42000) as n, count(*) as pools
           from d dd join gold.fct_validator_epoch e on e.epoch_height = dd.ep group by 1)
  select (select d1 - 60 from a) as from_day, (select count(*) from base) as pools_then,
         (select count(*) from gone) as pools, (select sum(stake_near) from gone) as stake,
         (select sum(stake_near) from gone) / (select sum(stake_near) from base) as share,
         (select median(stake_near) from gone) as median_stake,
         (select count(*) from gone where blocks_expected > 0) as producers,
         (select day from up) as upgrade_day, {SEC_UPGRADE} as upgrade_version,
         (select pools from d, up where d = up.day - 1) as pools_before_upgrade,
         (select count(*) from last_seen, up where last_seen.day < up.day) as before,
         (select count(*) from last_seen, up where last_seen.day < up.day and rate >= 0.95) as before_working,
         (select count(*) from last_seen, up where last_seen.day >= up.day) as after,
         (select count(*) from last_seen, up where last_seen.day >= up.day and coalesce(rate, 0) = 0) as after_idle,
         (select count(*) from last_seen where stake between 40000 and 42000) as band,
         (select max(n) from band) as band_most, (select arg_max(d, n) from band) as band_most_day,
         (select arg_max(pools, n) from band) as band_most_pools, (select n from band, a where d = d1) as band_now,
         (select count(*) from e1 join base b using (validator_account_id)
          where e1.blocks_expected > 0 and b.blocks_expected > 0) as producers_kept""")

# The ten largest one-day falls in pools seated, and the nearest day on which a new protocol version first shows in a
# day's first block. That header can lead the version in force, so a version's day here is "first seen".
SEC_VERSIONS = """
  ver as (select date_day as d, protocol_version as version
          from (select date_day, protocol_version, lag(protocol_version) over (order by date_day) as before
                from gold.dim_block_day where date_day >= date '2024-12-31')
          where protocol_version <> before)"""
sec_falls = table(f"""
  with {SEC}, {SEC_VERSIONS},
  steps as (select d, pools - lag(pools) over (order by d) as step from d)
  select s.d, s.step, (select min(abs(v.d - s.d)) from ver v) as days_from_a_version
  from steps s where s.step is not null order by s.step, s.d limit 10""")
sec_versions = table(f"""
  with {SEC_VERSIONS}
  select v.version, v.d, cast(u.first_block_utc as date) as in_force
  from ver v left join registry.protocol_upgrades u on u.protocol_version = v.version order by v.d""")

# What stakers are paid: new NEAR less the treasury's share, over the 30 days to the last full day and scaled to a
# year, with the yield and the issuance rate the Supply page prints for that day
sec_pay = one(f"""
  with p as (select sum(minted_near) as minted, sum(treasury_reward_near) as treasury
             from gold.fct_supply_daily where {D30})
  select {LAST} as day, (p.minted - p.treasury) * 365 / 30 as near_a_year, p.treasury / p.minted as treasury_share,
         (select price_usd from gold.fct_market_daily where date_day = {LAST}) as price,
         n.nominal_staking_yield_rate as yield, n.gross_inflation_rate as issuance
  from p, gold.fct_net_dilution_daily n where n.date_day = {LAST}""")
sec_yield_daily = columns(f"""
  select date_day as d, nominal_staking_yield_rate as paid from gold.fct_net_dilution_daily
  where nominal_staking_yield_rate is not null and date_day >= date '2025-01-01' and date_day <= {LAST}
  order by 1""", 6)

# Around the 2025 cut, which took effect during the day of the first halved reward (the Governance page's day): NEAR's
# close on the last full day before it and its lowest close since, and what stakers were paid between the middle of
# the 90 days before the cut and the middle of the newest 90 days of the validator series
sec_cut = one(f"""
  with {SEC}, c as (select date '{gov_cut_day}' as took)
  select c.took, (select price_usd from gold.fct_market_daily where date_day = c.took - 1) as price_before,
         (select min(price_usd) from gold.fct_market_daily where date_day > c.took and date_day <= {LAST}) as low,
         (select arg_min(date_day, price_usd) from gold.fct_market_daily
          where date_day > c.took and date_day <= {LAST}) as low_day,
         (select sum(minted_near - treasury_reward_near) from gold.fct_supply_daily, a
          where date_day > c.took - 45 and date_day <= a.d1 - 44) as paid_between,
         c.took - 44 as paid_from, (select d1 - 44 from a) as paid_to
  from c""")

# September 2026, when stake left fastest: four days of the daily series, chosen as days with no large pool missing
# from the epoch. The stake and NEAR's close on each, and the four pools that lost and gained the most.
SEP = {"start": "2026-09-07", "mid": "2026-09-15", "low": "2026-09-28", "back": "2026-10-19"}
sec_sep_days = table(f"""
  with {SEC}
  select d.d, d.stake, m.price_usd as price from d left join gold.fct_market_daily m on m.date_day = d.d
  where d.d in ({", ".join(f"date '{v}'" for v in SEP.values())}) order by 1""")
SEP_POOLS = f"""
  with {SEC},
  p as (select replace(replace(e.validator_account_id, '.poolv1.near', ''), '.pool.near', '') as pool,
               coalesce(sum(e.stake_near) filter (where dd.d = date '{SEP["start"]}'), 0) as s0,
               coalesce(sum(e.stake_near) filter (where dd.d = date '{SEP["low"]}'), 0) as s1,
               coalesce(sum(e.stake_near) filter (where dd.d = date '{SEP["back"]}'), 0) as s2
        from d dd join gold.fct_validator_epoch e on e.epoch_height = dd.ep
        where dd.d in (date '{SEP["start"]}', date '{SEP["low"]}', date '{SEP["back"]}') group by 1)"""
sec_september = {
    "days": SEP,
    "stake": {r["d"]: r["stake"] for r in sec_sep_days},
    "price": {r["d"]: clean(r["price"], 4) for r in sec_sep_days},
    "lost": table(f"{SEP_POOLS} select pool, s1 - s0 as change from p order by 2, 1 limit 4"),
    "gained": table(f"{SEP_POOLS} select pool, s2 - s1 as change from p order by 2 desc, 1 limit 4"),
}

# Chain Signatures: the signer set and how many of them a signature needs, by day. A row dated D is the contract's
# state at D's first block, so each day here is the close of the day before. Monthly before 2025, daily since.
sec_signers_daily = columns("""
  select snapshot_date - 1 as d, participants as signers, threshold as needed
  from gold.fct_mpc_state order by 1""", 0)
# The signers at the newest close, the first close at which each was in the set, and the node address NearBlocks lists
sec_signers = table("""
  with first_seen as (select operator_account_id, min(snapshot_date) as first_row from gold.fct_mpc_participants group by 1)
  select p.operator_account_id as signer, f.first_row - 1 as since, o.node_url as node
  from gold.fct_mpc_participants p join first_seen f using (operator_account_id)
  left join gold.fct_mpc_operators o on o.operator_account_id = p.operator_account_id
        and o.snapshot_date = (select max(snapshot_date) from gold.fct_mpc_operators)
  where p.snapshot_date = (select max(snapshot_date) from gold.fct_mpc_participants)
  order by f.first_row, p.operator_account_id""")
# Closes among the newest 30 at which one of today's signers was out of the set, having been in it before
sec_signer_gaps = table("""
  with days as (select snapshot_date from gold.fct_mpc_state order by snapshot_date desc limit 30),
       now as (select operator_account_id from gold.fct_mpc_participants
               where snapshot_date = (select max(snapshot_date) from gold.fct_mpc_participants)),
       first_seen as (select operator_account_id, min(snapshot_date) as first_row from gold.fct_mpc_participants group by 1)
  select n.operator_account_id as signer, d.snapshot_date - 1 as d
  from now n join first_seen f using (operator_account_id) join days d on d.snapshot_date > f.first_row
  where not exists (select 1 from gold.fct_mpc_participants p
                    where p.operator_account_id = n.operator_account_id and p.snapshot_date = d.snapshot_date)
  order by 1, 2""")
# Whether NearBlocks reports a secure enclave for any signer, on any nightly read (the staging table keeps the field).
# And signers whose account shares a name with a seated staking pool: matched by hand on names, so a reading of names.
SIGNER_POOLS = [("astrostakers-mainnet.near", "astro-stakers.poolv1.near"), ("bitwise-mpc01.near", "bitwise_1.poolv1.near"),
                ("bitwise-mpc01.near", "bitwise_2.poolv1.near"), ("svrn-01.near", "svrn.pool.near"),
                ("svrn-01.near", "svrn-ai.poolv1.near"), ("everstake-mpc-1.near", "everstake.poolv1.near"),
                ("stakin-mpc.near", "stakin.poolv1.near"), ("near-mpc-staking4all-01.near", "staking4all.poolv1.near"),
                ("multichain-mainnet-aurora.near", "aurora.pool.near"), ("nansen-ai-mpc.near", "nansen.poolv1.near")]
sec_signer_facts = one(f"""
  with {SEC},
  now as (select operator_account_id from gold.fct_mpc_participants
          where snapshot_date = (select max(snapshot_date) from gold.fct_mpc_participants)),
  nm as (select * from (values {", ".join(f"('{s}', '{p}')" for s, p in SIGNER_POOLS)}) as t(signer, pool))
  select (select count(distinct snapshot_date) from silver.stg_nearblocks__mpc_operators) as enclave_reads,
         (select count(*) from silver.stg_nearblocks__mpc_operators
          where tee_status is not null and tee_status not in ('', 'none')) as enclave_rows,
         (select count(distinct n.operator_account_id) from now n join nm on nm.signer = n.operator_account_id
          join e1 on e1.validator_account_id = nm.pool) as share_a_pool_name""")

security = {
    "now": {k: clean(v, 6) for k, v in sec_now.items()},
    "otherEpochs": sec_other_epochs,
    "leavers": {k: clean(v, 6) for k, v in sec_leavers.items()},
    "falls": sec_falls,
    "versions": sec_versions,
    "pay": {k: clean(v, 6) for k, v in sec_pay.items()},
    "yieldDaily": sec_yield_daily,
    "cut": {k: clean(v, 6) for k, v in sec_cut.items()},
    "september": sec_september,
    "signersDaily": sec_signers_daily,
    "signers": sec_signers,
    "signerGaps": sec_signer_gaps,
    "signerFacts": {k: clean(v) for k, v in sec_signer_facts.items()},
}

# NEAR Intents beside the other services that swap a token on one chain for a token on another: volume over the last
# three complete months (the scorecard's quarter) and over the 30 days to the newest day. The figures are of two kinds,
# the swaps a service settled and the tokens sent through it across chains, and figure_kind says which a row is.
rivals = table(f"""
  select service_id, service_name, figure_kind, is_near_intents,
         sum(volume_usd) filter (where date_day >= {MKT_Q_END} - interval 3 month and date_day < {MKT_Q_END}) as vol_q,
         count(*) filter (where date_day >= {MKT_Q_END} - interval 3 month and date_day < {MKT_Q_END} and volume_usd > 0) as days_q,
         sum(volume_usd) filter (where date_day > {LAST} - interval 30 day and date_day <= {LAST}) as vol_30d
  from gold.fct_swap_services_daily
  group by 1, 2, 3, 4
  order by vol_q desc nulls last, service_id""", 0)

# THE HORIZON. Years for Intents volume to reach the break-even multiple at the growth measured over the last year and
# at three round rates, today and at the end of HSP-029's ramp. The rows and the query come from tools/horizon.py, which
# THESIS.md reads too, so both print the same years. years_to_breakeven is null when a pace is not above zero.
from tools.horizon import HORIZON_SQL, horizon as horizon_rows  # noqa: E402

horizon = {"sql": HORIZON_SQL, "rows": [{k: clean(v, 6) for k, v in r.items()} for r in horizon_rows(con)]}

# THE POOL'S HISTORY, READ FROM THE CHAIN. At each month end the intents.near contract's balances of wNEAR, the
# stablecoins and the pool's other main assets, valued at prices from outside NEAR, beside the dashboard's value of
# the same assets that day. The query is the one the page shows. The facts say how much of the pool the tokens read
# cover on the dashboard's newest day, and which assets have no price.
POOL_HISTORY_SQL = """-- NEAR Intents' main tokens at each month end: intents.near's balances read from the chain and valued at
-- prices from outside NEAR (a stablecoin at one dollar), beside the value NEAR's dashboard gives the same assets
-- that day. An asset counts among the others only on a day when every token of it has a price.
with chain as (
  select date_day,
         sum(amount_token) filter (where token_class = 'native_wrapped') as near_on_chain,
         sum(value_usd) filter (where token_class = 'native_wrapped') as near_chain_usd,
         sum(value_usd) filter (where token_class = 'stablecoin') as stablecoins_chain_usd
  from gold.fct_intents_pool_chain_monthly
  group by 1
), others as (
  select c.date_day, c.dashboard_symbol, sum(c.value_usd) as chain_usd, max(d.tvl_usd) as dashboard_usd
  from gold.fct_intents_pool_chain_monthly c
  join gold.fct_dune_intents_tvl_asset_daily d on d.symbol = c.dashboard_symbol and d.date_day = c.date_day
  where c.token_class = 'other'
  group by 1, 2
  having count(c.value_usd) = count(*) and max(d.tvl_usd) > 0
), dashboard as (
  select date_day,
         sum(tvl_usd) filter (where symbol = 'wNEAR') as near_dashboard_usd,
         sum(tvl_usd) filter (where upper(symbol) in (select upper(symbol) from gold.fct_intents_pool_chain_monthly
                                                      where token_class = 'stablecoin')) as stablecoins_dashboard_usd
  from gold.fct_dune_intents_tvl_asset_daily
  group by 1
)
select c.date_day, c.near_on_chain, c.near_chain_usd, d.near_dashboard_usd,
       c.stablecoins_chain_usd, d.stablecoins_dashboard_usd,
       o.others_chain_usd, o.others_dashboard_usd, o.other_assets_priced
from chain c
join dashboard d using (date_day)
left join (select date_day, sum(chain_usd) as others_chain_usd, sum(dashboard_usd) as others_dashboard_usd,
                  count(*) as other_assets_priced
           from others group by 1) o using (date_day)
order by 1;"""
pool_history_facts = one("""
  with read as (select distinct dashboard_symbol as symbol from gold.fct_intents_pool_chain_monthly where dashboard_symbol is not null),
       newest as (select * from gold.fct_dune_intents_tvl_asset_daily
                  where date_day = (select max(date_day) from gold.fct_dune_intents_tvl_asset_daily)),
       last_read as (select * from gold.fct_intents_pool_chain_monthly
                     where date_day = (select max(date_day) from gold.fct_intents_pool_chain_monthly))
  select (select sum(share_of_day) from newest where symbol in (select symbol from read)) as covered_share,
         (select max(date_day) from newest) as dashboard_day,
         (select min(date_day) from gold.fct_intents_pool_chain_monthly) as first_chain_day,
         (select count(distinct date_day) from gold.fct_intents_pool_chain_monthly where is_month_end) as month_ends,
         (select count(distinct dashboard_symbol) from last_read where token_class = 'other') as other_assets,
         (select count(distinct symbol) from last_read where token_class = 'stablecoin') as stablecoin_symbols,
         (select string_agg(distinct dashboard_symbol, ', ' order by dashboard_symbol) from last_read
          where token_class = 'other' and value_status = 'no_price') as unpriced""")
pool_history = {
    "sql": POOL_HISTORY_SQL,
    "rows": table(POOL_HISTORY_SQL.rstrip(";"), 0),
    "facts": {k: clean(v, 6) for k, v in pool_history_facts.items()},
}

# NEAR'S PUBLIC BIGQUERY DATASET, for three questions. Which contracts the accounts that sign transactions call: the
# newest day's leading contracts by signers, and three counts on every day read. Whether accounts come back: the share
# of the accounts that first signed in a year that signed again 1, 2, 3, 6 and 12 months later, complete months only.
# The third, BigQuery against NearBlocks, reads dq_reconciliation, exported above as recon. Each query is the one the
# page shows. A warehouse without these tables exports None for that part, and the page leaves its question out.
BQ_HAVE = {r["table_name"] for r in rows("select table_name from information_schema.tables where table_schema = 'gold'")}
BQ_NEWEST = f"(select max(date_day) from gold.fct_bigquery_contract_daily where date_day <= {LAST})"
BQ_CONTRACTS_SQL = f"""-- The contracts that the most accounts signed a call to on the newest day read from NEAR's public BigQuery dataset,
-- with NEAR Intents' contract always listed. A signer is the account that signed the transaction a call came from;
-- for a relayed call that is the relayer. signer_share is of the day's accounts that signed any function call: one
-- that called several contracts counts under each, so the shares do not add up to 100%. The dataset is read for each
-- day's largest contracts only, by calls, by signers and by callers.
select date_day, contract_id, entity, signers, signer_share, function_calls, rank_by_signers, rank_by_calls
from gold.fct_bigquery_contract_daily
where date_day = {BQ_NEWEST}
  and (rank_by_signers <= 10 or contract_id = 'intents.near')
order by rank_by_signers, contract_id;"""
BQ_DAYS_SQL = f"""-- Every day read: the accounts that signed a transaction leading to a function call, how many of them called the
-- newest day's leading contract and NEAR Intents' contract, the leader's rank by signers that day, and the function
-- calls Intents' contract received.
with leader as (
  select contract_id
  from gold.fct_bigquery_contract_daily
  where date_day = {BQ_NEWEST}
  order by rank_by_signers, contract_id
  limit 1
)
select a.date_day,
       a.signers as all_signers,
       max(c.signers) filter (where c.contract_id = (select contract_id from leader)) as leader_signers,
       max(c.rank_by_signers) filter (where c.contract_id = (select contract_id from leader)) as leader_rank,
       max(c.signers) filter (where c.contract_id = 'intents.near') as intents_signers,
       max(c.function_calls) filter (where c.contract_id = 'intents.near') as intents_calls
from gold.fct_bigquery_action_daily a
left join gold.fct_bigquery_contract_daily c using (date_day)
where a.action_kind = 'FUNCTION_CALL' and a.date_day <= {LAST}
group by 1, 2
order by 1;"""
BQ_COHORTS_SQL = """-- Do accounts come back? NEAR's public BigQuery dataset places every account that ever signed a transaction in the
-- month it first signed one. Each row is a year of those months: the share of its accounts that signed again 1, 2, 3,
-- 6 and 12 months later. Only complete months count, so a share is over the months of that year whose later month
-- is complete.
with cohorts as (
  select cohort_month, cohort_signers
  from gold.fct_bigquery_signer_cohort_monthly
  where months_since_first = 0
), complete as (
  select max(active_month) as last_month
  from gold.fct_bigquery_signer_cohort_monthly
  where is_active_month_complete
), later as (
  select unnest([1, 2, 3, 6, 12]) as months_later
)
select year(c.cohort_month) as first_signed_year, l.months_later,
       count(*) as cohort_months,
       sum(c.cohort_signers) as accounts,
       coalesce(sum(r.signers), 0) as signed_again,
       coalesce(sum(r.signers), 0) / sum(c.cohort_signers) as retained_share
from cohorts c
cross join later l
cross join complete m
left join gold.fct_bigquery_signer_cohort_monthly r
  on r.cohort_month = c.cohort_month and r.months_since_first = l.months_later
where c.cohort_month + to_months(l.months_later) <= m.last_month
group by 1, 2
order by 1, 2;"""
BQ_TRAFFIC_SQL = f"""-- The share of each day's transactions that were sent to NEAR Intents' contract, intents.near, as NEAR's public
-- BigQuery dataset counts them, from the first day of the six months the scorecard's test reads. The test holds the
-- share over the last three complete months against the share over the three before. rank_by_txns is the contract's
-- place among the day's receivers by transactions.
select c.date_day, c.txns as all_txns, coalesce(r.txns, 0) as intents_txns,
       coalesce(r.txns, 0) / c.txns as share, r.rank_by_txns
from gold.fct_bigquery_chain_daily c
left join gold.fct_bigquery_receiver_daily r
  on r.date_day = c.date_day and r.receiver_account_id = 'intents.near'
where c.is_day_complete and c.txns is not null
  and c.date_day >= (select date_trunc('month', as_of_date) - interval 5 month from gold.fct_thesis_scorecard
                     where claim_id = 'intents_share_of_transactions_is_rising')
  and c.date_day <= {LAST}
order by 1;"""
bigquery = {"contracts": None, "days": None, "cohorts": None, "traffic": None, "game": None, "deploys": None, "blocks": None,
            "inUse": None, "receivers": None, "firstSigners": None, "stableSenders": None, "rheaUse": None,
            "senders": None, "split": None, "sigCallers": None, "stakeOwners": None}
# For the table of what an outsider can still count: the transactions the Intents contract received, counted from
# the public chain, over the same two months as the other counts
if "fct_bigquery_receiver_daily" in BQ_HAVE:
    chain_txns = {r["m"]: r["chain_txns"] for r in table(f"""
      select cast(date_trunc('month', date_day) as date) m, avg(txns) chain_txns
      from gold.fct_bigquery_receiver_daily
      where receiver_account_id = 'intents.near'
        and date_day <= {LAST} and date_day >= date_trunc('month', {LAST} - interval 1 month)
      group by 1""", 4)}
    for r in outside_counts:
        r["chain_txns"] = chain_txns.get(r["m"])
if {"fct_bigquery_contract_daily", "fct_bigquery_action_daily"} <= BQ_HAVE:
    bigquery["contracts"] = {"sql": BQ_CONTRACTS_SQL, "rows": table(BQ_CONTRACTS_SQL.rstrip(";"), 6)}
    bigquery["days"] = {"sql": BQ_DAYS_SQL, "cols": columns(BQ_DAYS_SQL.rstrip(";"), 6)}
if {"fct_bigquery_signer_cohort_monthly", "fct_bigquery_action_daily"} <= BQ_HAVE:
    bigquery["cohorts"] = {
        "sql": BQ_COHORTS_SQL,
        "rows": table(BQ_COHORTS_SQL.rstrip(";"), 6),
        # How many accounts ever signed, and one complete month's signers by whether they first signed before that
        # month's year. An account signs its own deletion, so a month in which accounts are deleted in bulk counts
        # them as signers (579,000 of October 2026's 827,000). The month read is the newest complete one in which
        # the signers of a deletion are under a tenth of all signers; a newer month passed over is named with its
        # counts, so the page can say why. Deletions are counted from the day the actions are read.
        "facts": {k: clean(v, 6) for k, v in one("""
          with months as (
            select active_month, sum(signers) as signed,
                   sum(signers) filter (where year(cohort_month) < year(active_month)) as older
            from gold.fct_bigquery_signer_cohort_monthly where is_active_month_complete group by 1),
          gone as (
            select cast(date_trunc('month', date_day) as date) as active_month, sum(signers) as deleted
            from gold.fct_bigquery_action_daily where action_kind = 'DELETE_ACCOUNT' group by 1),
          m as (
            select months.*, coalesce(gone.deleted, 0) as deleted,
                   row_number() over (order by months.active_month desc) as back
            from months left join gone using (active_month)),
          pick as (
            select * from m where deleted < 0.1 * signed or back = (select max(back) from m)
            order by back limit 1)
          select (select sum(cohort_signers) from gold.fct_bigquery_signer_cohort_monthly
                  where months_since_first = 0) as accounts_ever,
                 pick.active_month as last_month,
                 pick.signed as signed_last_month,
                 pick.older as signed_last_month_older,
                 newest.active_month as skipped_month,
                 newest.signed as skipped_signed,
                 newest.deleted as skipped_deleted
          from pick left join m as newest on newest.back = 1 and pick.back > 1""").items()},
    }

# The claim on Intents' share of the chain's transactions: the two quarters it reads, the days since, and the same
# quarters of the volume NEAR reports, so the page can set the chain's record beside NEAR's own series. The page's
# shares must be the scorecard's measurement.
share_claim = next((r for r in scorecard if r["claim_id"] == "intents_share_of_transactions_is_rising"), None)
if share_claim and {"fct_bigquery_receiver_daily", "fct_bigquery_chain_daily"} <= BQ_HAVE:
    traffic_facts = one(f"""
      with q as (select as_of_date as end_day, cast(date_trunc('month', as_of_date) as date) as last_month
                 from gold.fct_thesis_scorecard where claim_id = 'intents_share_of_transactions_is_rising'),
           d as (select c.date_day, c.txns as all_txns, coalesce(r.txns, 0) as intents_txns, r.rank_by_txns,
                        c.date_day >= q.last_month - interval 2 month and c.date_day <= q.end_day as now,
                        c.date_day >= q.last_month - interval 5 month and c.date_day < q.last_month - interval 2 month as before,
                        c.date_day > q.end_day as since
                 from gold.fct_bigquery_chain_daily c
                 left join gold.fct_bigquery_receiver_daily r
                   on r.date_day = c.date_day and r.receiver_account_id = 'intents.near'
                 cross join q
                 where c.is_day_complete and c.txns is not null and c.date_day <= {LAST})
      select (select end_day from q) as end_day,
             sum(intents_txns) filter (where now) / sum(all_txns) filter (where now) as share_now,
             sum(intents_txns) filter (where before) / sum(all_txns) filter (where before) as share_before,
             sum(intents_txns) filter (where now) / sum(intents_txns) filter (where before) - 1 as txns_change,
             sum(intents_txns) filter (where since) / sum(all_txns) filter (where since) as share_since,
             count(*) filter (where since) as days_since,
             count(*) filter (where since and rank_by_txns = 1) as days_first_since,
             avg(intents_txns) filter (where since)
               / avg(intents_txns) filter (where date_day >= (select last_month from q) and not since) - 1 as txns_since_change,
             max(date_day) as newest_day
      from d""")
    # The same days of the volume NEAR reports: the days since the last complete month against that month, by day
    traffic_facts["volume_since_change"] = one(f"""
      with q as (select as_of_date as end_day, cast(date_trunc('month', as_of_date) as date) as last_month
                 from gold.fct_thesis_scorecard where claim_id = 'intents_share_of_transactions_is_rising')
      select avg(volume_usd) filter (where date_day > q.end_day)
               / avg(volume_usd) filter (where date_day <= q.end_day) - 1 as v
      from gold.fct_intents_daily, q
      where date_day >= q.last_month and date_day <= {LAST} and volume_usd is not null""")["v"]
    # Two counts of the contract's place over the same 30 days: transactions sent to it, as BigQuery counts them, and
    # transactions that touch it, as NearBlocks counts them (the count the rest of the Usage page uses)
    traffic_facts["sent_30d"] = one(f"""
      select sum(coalesce(r.txns, 0)) / sum(c.txns) as v
      from gold.fct_bigquery_chain_daily c
      left join gold.fct_bigquery_receiver_daily r
        on r.date_day = c.date_day and r.receiver_account_id = 'intents.near'
      where c.is_day_complete and c.txns is not null and {D30.replace('date_day', 'c.date_day')}""")["v"]
    traffic_facts["touch_30d"] = one(f"""
      select sum(intents_txns) / sum(txns_ex_batch_streams) as v
      from gold.fct_usage_quality_daily where {D30}""")["v"]
    traffic_facts["volume_change"] = one("""
      with q as (select cast(date_trunc('month', as_of_date) as date) as last_month from gold.fct_thesis_scorecard
                 where claim_id = 'intents_share_of_transactions_is_rising')
      select sum(volume_usd) filter (where month_start >= q.last_month - interval 2 month)
               / sum(volume_usd) filter (where month_start < q.last_month - interval 2 month) - 1 as v
      from gold.fct_intents_unit_economics_monthly, q
      where is_month_complete and month_start >= q.last_month - interval 5 month and month_start <= q.last_month""")["v"]
    if abs(float(traffic_facts["share_now"]) - float(traffic_facts["share_before"]) - float(share_claim["value"])) > 1e-6:
        sys.exit("The Usage page: Intents' share of transactions here is not what the scorecard measures")
    bigquery["traffic"] = {"sql": BQ_TRAFFIC_SQL, "cols": columns(BQ_TRAFFIC_SQL.rstrip(";"), 6),
                           "facts": {k: clean(v, 6) for k, v in traffic_facts.items()}}
# What the signer count is made of: over the newest 30 days read and the 30 days ending 180 days earlier, the accounts
# that signed any transaction, those that called the contract most accounts call, and the accounts that did not call
# it. A median for those outside, because a day of account deletions lifts the count for that day alone.
if {"fct_bigquery_contract_daily", "fct_bigquery_chain_daily"} <= BQ_HAVE:
    game_facts = one(f"""
      with leader as (select contract_id from gold.fct_bigquery_contract_daily
                      where date_day = {BQ_NEWEST} order by rank_by_signers, contract_id limit 1),
           d as (select c.date_day, c.signers as everyone, g.signers as game, g.contract_id,
                        c.date_day > e.d - 30 as newest, c.date_day <= e.d - 180 and c.date_day > e.d - 210 as before
                 from gold.fct_bigquery_chain_daily c
                 join gold.fct_bigquery_contract_daily g
                   on g.date_day = c.date_day and g.contract_id = (select contract_id from leader)
                 cross join (select {BQ_NEWEST} as d) e)
      select max(contract_id) as contract_id,
             sum(game) filter (where newest) / sum(everyone) filter (where newest) as share,
             avg(game) filter (where newest) as game_now, avg(game) filter (where before) as game_before,
             median(everyone - game) filter (where newest) as outside_now,
             median(everyone - game) filter (where before) as outside_before,
             count(*) filter (where newest) as days_now, count(*) filter (where before) as days_before
      from d""")
    if game_facts["days_now"] == 30 and game_facts["days_before"] == 30:
        bigquery["game"] = {k: clean(v, 6) for k, v in game_facts.items()}

# A query the page shows, without its closing "order by", so that the facts can be read from the same rows
unordered = lambda sql: sql.rstrip().rstrip(";").rsplit("order by", 1)[0]

# CODE PUT ON CHAIN, for the Developers page. BigQuery counts each deploy action, the accounts that received code and
# the accounts that signed a deploy, so the count is documented and says how many accounts are behind it. An account
# that takes up code already on chain (a global contract) is a copy of one program and is counted apart. The facts
# set the newest 30 days read against the first 30.
BQ_DEPLOYS_SQL = f"""-- Code put on chain each day, as NEAR's public BigQuery dataset counts it: the deploys, the accounts that received
-- code, the accounts that signed a deploy, and the accounts that took up code already on chain (a global contract),
-- which copies one program and is not a deploy. A day with no deploy counts as zero.
select date_day,
       coalesce(max(actions) filter (where action_kind = 'DEPLOY_CONTRACT'), 0) as deploys,
       coalesce(max(receivers) filter (where action_kind = 'DEPLOY_CONTRACT'), 0) as accounts_given_code,
       coalesce(max(signers) filter (where action_kind = 'DEPLOY_CONTRACT'), 0) as accounts_signing,
       coalesce(max(receivers) filter (where action_kind = 'USE_GLOBAL_CONTRACT'), 0) as accounts_taking_shared_code
from gold.fct_bigquery_action_daily
where date_day <= {LAST}
group by 1
order by 1;"""
if "fct_bigquery_action_daily" in BQ_HAVE:
    deploy_cols = columns(BQ_DEPLOYS_SQL.rstrip(";"), 0)
    if deploy_cols and len(deploy_cols["date_day"]) >= 60:
        deploy_facts = one(f"""
          with d as ({unordered(BQ_DEPLOYS_SQL)}),
               e as (select min(date_day) as first_day, max(date_day) as last_day from d)
          select e.first_day, e.last_day,
                 count(*) filter (where d.date_day > e.last_day - 30) as days_now,
                 count(*) filter (where d.date_day < e.first_day + 30) as days_first,
                 avg(deploys) filter (where d.date_day > e.last_day - 30) as deploys_now,
                 avg(deploys) filter (where d.date_day < e.first_day + 30) as deploys_first,
                 avg(accounts_given_code) filter (where d.date_day > e.last_day - 30) as given_now,
                 avg(accounts_given_code) filter (where d.date_day < e.first_day + 30) as given_first,
                 avg(accounts_signing) filter (where d.date_day > e.last_day - 30) as signers_now,
                 avg(accounts_signing) filter (where d.date_day < e.first_day + 30) as signers_first,
                 avg(accounts_taking_shared_code) filter (where d.date_day > e.last_day - 30) as shared_now,
                 avg(accounts_taking_shared_code) filter (where d.date_day < e.first_day + 30) as shared_first
          from d cross join e group by 1, 2""")
        bigquery["deploys"] = {"sql": BQ_DEPLOYS_SQL, "cols": deploy_cols,
                               "facts": {k: clean(v, 2) for k, v in deploy_facts.items()}}

# HOW MANY CONTRACTS ARE IN USE, for the Developers page: the contracts that received a function call each day. The
# facts set the newest 30 days read against the first 30, and name the lowest complete month.
BQ_IN_USE_SQL = f"""-- Contracts that received a function call each day, as NEAR's public BigQuery dataset counts them
select date_day, receivers as contracts_called
from gold.fct_bigquery_action_daily
where action_kind = 'FUNCTION_CALL' and date_day <= {LAST}
order by 1;"""
if "fct_bigquery_action_daily" in BQ_HAVE:
    in_use_cols = columns(BQ_IN_USE_SQL.rstrip(";"), 0)
    if in_use_cols and len(in_use_cols["date_day"]) >= 60:
        in_use_facts = one(f"""
          with d as ({unordered(BQ_IN_USE_SQL)}),
               e as (select min(date_day) as first_day, max(date_day) as last_day from d)
          select e.first_day, e.last_day,
                 count(*) filter (where d.date_day > e.last_day - 30) as days_now,
                 count(*) filter (where d.date_day < e.first_day + 30) as days_first,
                 avg(contracts_called) filter (where d.date_day > e.last_day - 30) as called_now,
                 avg(contracts_called) filter (where d.date_day < e.first_day + 30) as called_first
          from d cross join e group by 1, 2""")
        in_use_low = one(f"""
          with m as (select cast(date_trunc('month', date_day) as date) as mth, avg(contracts_called) as called
                     from ({unordered(BQ_IN_USE_SQL)}) group by 1 having count(*) = day(last_day(min(date_day))))
          select mth as low_month, called as low_called from m order by 2, 1 limit 1""")
        bigquery["inUse"] = {"sql": BQ_IN_USE_SQL, "cols": in_use_cols,
                             "facts": {**{k: clean(v, 1) for k, v in in_use_facts.items()},
                                       **{k: clean(v, 1) for k, v in in_use_low.items()}}}

# WHO RECEIVES THE TRANSACTIONS, COUNTED EXACTLY, for the Usage page. BigQuery is read for each day's 25 largest
# receivers. Each transaction has one receiver, so a group's share can be ranked, which the block sample cannot do.
BQ_RECEIVERS_SQL = f"""-- The last 30 days' transactions by who received them, for each day's 25 largest receivers, as NEAR's public
-- BigQuery dataset counts them. Each transaction has one receiver, so the shares can be added; what is left of 100%
-- went to smaller accounts, among them the users' own accounts that a relayer sends to.
with days as (
  select sum(txns) as all_txns
  from gold.fct_bigquery_chain_daily
  where is_day_complete and {D30}
)
select coalesce(nullif(nullif(entity, ''), 'Unlabelled'), 'No label') as receiver_group,
       count(distinct receiver_account_id) as accounts,
       sum(txns) as txns,
       sum(txns) / (select all_txns from days) as share
from gold.fct_bigquery_receiver_daily
where rank_by_txns <= 25 and {D30}
group by 1
order by 3 desc, 1;"""
if {"fct_bigquery_receiver_daily", "fct_bigquery_chain_daily"} <= BQ_HAVE:
    receiver_rows = table(BQ_RECEIVERS_SQL.rstrip(";"), 6)
    receiver_days = one(f"select count(distinct date_day) as n from gold.fct_bigquery_receiver_daily where {D30}")["n"]
    if receiver_rows and receiver_days == 30:
        bigquery["receivers"] = {"sql": BQ_RECEIVERS_SQL, "rows": receiver_rows,
                                 "facts": {"covered": clean(sum(r["share"] for r in receiver_rows), 6)}}

# IS NEAR ADDING ACCOUNTS, for the Usage page: the accounts that signed their first transaction, by month, over the
# newest 18 complete months and the month in progress. read_through is the last day the month in progress was read to.
BQ_FIRST_SQL = f"""-- Accounts that signed their first transaction, by month, as NEAR's public BigQuery dataset places them. The
-- newest month is not complete: read_through is the last day it was read to.
select cohort_month as month, cohort_signers as first_time_signers,
       is_active_month_complete as is_month_complete, read_through
from gold.fct_bigquery_signer_cohort_monthly
where months_since_first = 0
  and cohort_month >= date_trunc('month', {LAST}) - interval 18 month
order by 1;"""
if "fct_bigquery_signer_cohort_monthly" in BQ_HAVE:
    first_cols = columns(BQ_FIRST_SQL.rstrip(";"), 0)
    if first_cols and len(first_cols["month"]) >= 13:
        first_facts = one(f"""
          with d as ({unordered(BQ_FIRST_SQL)}),
               c as (select * from d where is_month_complete),
               n as (select max(month) as last_month from c)
          select n.last_month,
                 max(first_time_signers) filter (where c.month = n.last_month) as last_signers,
                 max(first_time_signers) filter (where c.month = n.last_month - interval 12 month) as year_ago_signers,
                 arg_min(c.month, first_time_signers) filter (where c.month > n.last_month - interval 12 month) as low_month,
                 min(first_time_signers) filter (where c.month > n.last_month - interval 12 month) as low_signers
          from c cross join n group by 1""")
        first_open = rows(f"""
          select month, first_time_signers, read_through, datediff('day', month, read_through) + 1 as days_read
          from ({unordered(BQ_FIRST_SQL)}) where not is_month_complete order by 1 desc limit 1""")
        bigquery["firstSigners"] = {"sql": BQ_FIRST_SQL, "cols": first_cols,
                                    "facts": {**{k: clean(v, 0) for k, v in first_facts.items()},
                                              "open": {k: clean(v, 0) for k, v in first_open[0].items()} if first_open else None}}

# WHO USES THE STABLECOINS ON NEAR, for the Capital page: the accounts a day that signed a transaction sent to
# Tether's and Circle's token contracts, and the transactions those contracts received. The facts set the newest 30
# days against the same 30 days a year earlier.
BQ_STABLE_SQL = f"""-- Accounts a day that signed a transaction sent to Tether's and Circle's token contracts on NEAR, and the
-- transactions those contracts received, as NEAR's public BigQuery dataset counts them
select date_day,
       max(signers) filter (where entity = 'Tether') as tether_accounts,
       max(signers) filter (where entity = 'Circle') as circle_accounts,
       max(txns) filter (where entity = 'Tether') as tether_txns,
       max(txns) filter (where entity = 'Circle') as circle_txns
from gold.fct_bigquery_receiver_daily
where category = 'stablecoin' and date_day <= {LAST}
group by 1
order by 1;"""
if "fct_bigquery_receiver_daily" in BQ_HAVE:
    stable_cols = columns(BQ_STABLE_SQL.rstrip(";"), 0)
    stable_one = one("""select count(distinct receiver_account_id) filter (where entity = 'Tether') as t,
                               count(distinct receiver_account_id) filter (where entity = 'Circle') as c
                        from gold.fct_bigquery_receiver_daily where category = 'stablecoin'""")
    if stable_cols and len(stable_cols["date_day"]) >= 400 and stable_one["t"] == 1 and stable_one["c"] == 1:
        stable_facts = one(f"""
          with d as ({unordered(BQ_STABLE_SQL)}),
               e as (select max(date_day) as last_day from d),
               w as (select d.*, d.date_day > e.last_day - 30 as now,
                            d.date_day > e.last_day - 395 and d.date_day <= e.last_day - 365 as ago
                     from d cross join e)
          select count(tether_accounts) filter (where now) as tether_days_now, count(circle_accounts) filter (where now) as circle_days_now,
                 count(tether_accounts) filter (where ago) as tether_days_ago, count(circle_accounts) filter (where ago) as circle_days_ago,
                 avg(tether_accounts) filter (where now) as tether_now, avg(tether_accounts) filter (where ago) as tether_ago,
                 avg(circle_accounts) filter (where now) as circle_now, avg(circle_accounts) filter (where ago) as circle_ago,
                 avg(tether_txns) filter (where now) as tether_txns_now, avg(tether_txns) filter (where ago) as tether_txns_ago,
                 avg(circle_txns) filter (where now) as circle_txns_now, avg(circle_txns) filter (where ago) as circle_txns_ago
          from w""")
        if min(stable_facts[k] for k in ("tether_days_now", "circle_days_now", "tether_days_ago", "circle_days_ago")) == 30:
            bigquery["stableSenders"] = {"sql": BQ_STABLE_SQL, "cols": stable_cols,
                                         "facts": {k: clean(v, 1) for k, v in stable_facts.items()}}

# HOW MUCH RHEA'S EXCHANGE IS USED, for the Capital page: the accounts a day that signed a call to its exchange
# contract, and the calls it received. The facts: the newest 30 days read, the first 30, and the highest complete month.
BQ_RHEA_SQL = f"""-- Accounts a day that signed a call to Rhea's exchange contract, v2.ref-finance.near, and the calls it received,
-- as NEAR's public BigQuery dataset counts them
select date_day, signers as accounts, function_calls as calls
from gold.fct_bigquery_contract_daily
where contract_id = 'v2.ref-finance.near' and date_day <= {LAST}
order by 1;"""
if "fct_bigquery_contract_daily" in BQ_HAVE:
    rhea_cols = columns(BQ_RHEA_SQL.rstrip(";"), 0)
    if rhea_cols and len(rhea_cols["date_day"]) >= 60:
        rhea_facts = one(f"""
          with d as ({unordered(BQ_RHEA_SQL)}),
               e as (select min(date_day) as first_day, max(date_day) as last_day from d)
          select e.first_day, e.last_day,
                 count(*) filter (where d.date_day > e.last_day - 30) as days_now,
                 count(*) filter (where d.date_day < e.first_day + 30) as days_first,
                 avg(accounts) filter (where d.date_day > e.last_day - 30) as accounts_now,
                 avg(accounts) filter (where d.date_day < e.first_day + 30) as accounts_first,
                 avg(calls) filter (where d.date_day > e.last_day - 30) as calls_now,
                 avg(calls) filter (where d.date_day < e.first_day + 30) as calls_first
          from d cross join e group by 1, 2""")
        rhea_peak = one(f"""
          with m as (select cast(date_trunc('month', date_day) as date) as mth, avg(accounts) as accounts
                     from ({unordered(BQ_RHEA_SQL)}) group by 1 having count(*) = day(last_day(min(date_day))))
          select mth as peak_month, accounts as peak_accounts from m order by 2 desc, 1 limit 1""")
        if rhea_facts["days_now"] >= 28 and rhea_facts["days_first"] >= 28:
            bigquery["rheaUse"] = {"sql": BQ_RHEA_SQL, "cols": rhea_cols,
                                   "facts": {**{k: clean(v, 1) for k, v in rhea_facts.items()},
                                             **{k: clean(v, 1) for k, v in rhea_peak.items()}}}

# WHO SENDS NEAR INTENTS' CONTRACT ITS TRANSACTIONS, for the Usage page. BigQuery counts each day's largest signers of
# the transactions the contract received. The two largest over the newest 30 days are drawn against all the others.
if "fct_bigquery_signer_daily" in BQ_HAVE:
    sender_top = table(f"""
      with t as (select sum(day_intents_txns) as total from (select distinct date_day, day_intents_txns
                 from gold.fct_bigquery_signer_daily where {D30}))
      select signer_account_id, max(entity) as entity, sum(intents_txns) / (select total from t) as share
      from gold.fct_bigquery_signer_daily where intents_txns > 0 and {D30}
      group by 1 order by 3 desc, 1 limit 2""", 6)
    if len(sender_top) == 2 and sender_top[0]["signer_account_id"] == "intents.near":
        SECOND = sender_top[1]["signer_account_id"]
        BQ_SENDERS_SQL = f"""-- Who signed the transactions NEAR Intents' contract received each day, as NEAR's public BigQuery dataset counts
-- them: the contract's own account, the largest other sender over the last 30 days, and everyone else
select date_day,
       max(day_intents_txns) as intents_txns,
       max(day_intents_signers) as signers,
       coalesce(sum(intents_txns) filter (where signer_account_id = 'intents.near'), 0)
         / max(day_intents_txns) as own_account_share,
       coalesce(sum(intents_txns) filter (where signer_account_id = '{SECOND}'), 0)
         / max(day_intents_txns) as second_sender_share
from gold.fct_bigquery_signer_daily
where day_intents_txns > 0 and date_day <= {LAST}
group by 1
order by 1;"""
        sender_facts = one(f"""
          select (select min(date_day) from gold.fct_bigquery_signer_daily
                  where signer_account_id = '{SECOND}' and intents_txn_share >= 0.01) as second_first_day,
                 (select avg(n) from (select distinct date_day, day_intents_signers as n
                  from gold.fct_bigquery_signer_daily where {D30})) as signers_30d,
                 (select count(distinct date_day) from gold.fct_bigquery_signer_daily where {D30}) as days_30d""")
        if sender_facts["days_30d"] == 30:
            bigquery["senders"] = {"sql": BQ_SENDERS_SQL, "cols": columns(BQ_SENDERS_SQL.rstrip(";"), 6),
                                   "facts": {"own_30d": sender_top[0]["share"], "second_id": SECOND,
                                             "second_entity": sender_top[1]["entity"], "second_30d": sender_top[1]["share"],
                                             **{k: clean(v, 1) for k, v in sender_facts.items()}}}

# TRANSACTIONS BY WHO SIGNED THEM, for the Usage page. By signer the two batch streams are three accounts, so they
# can be read back to the first day BigQuery was read, before NearBlocks' per-account statistics begin. An account
# outside a day's 25 largest signers falls under all others. The facts: the streams' share over the first and the last
# full quarter they ran, everything else over the first and the newest 30 days, and how far this count of the streams
# is from NearBlocks' over the days both hold.
BQ_SPLIT_SQL = f"""-- Transactions a day by who signed them, as NEAR's public BigQuery dataset counts them: the two batch streams
-- (three accounts), Sweat's relayer, and every other signer. An account outside a day's 25 largest signers is
-- counted under all others.
with days as (
  select date_day, max(day_txns) as all_txns,
         coalesce(sum(txns) filter (where signer_account_id in ('hotwallet.kaiching', 'users.kaiching', 'sweat-migration.near')), 0) as batch_stream_txns,
         coalesce(sum(txns) filter (where signer_account_id = 'sweat-relayer.near'), 0) as sweat_relayer_txns
  from gold.fct_bigquery_signer_daily
  where date_day <= {LAST}
  group by 1
)
select date_day, batch_stream_txns, sweat_relayer_txns,
       all_txns - batch_stream_txns - sweat_relayer_txns as other_txns
from days
order by 1;"""
if "fct_bigquery_signer_daily" in BQ_HAVE:
    split_cols = columns(BQ_SPLIT_SQL.rstrip(";"), 0)
    if split_cols and len(split_cols["date_day"]) >= 400:
        split_facts = one(f"""
          with d as ({unordered(BQ_SPLIT_SQL)}),
               e as (select min(date_day) as first_day, max(date_day) as last_day,
                            max(date_day) filter (where batch_stream_txns > 0.01 * (batch_stream_txns + sweat_relayer_txns + other_txns)) as stop_day from d),
               q as (select cast(date_trunc('quarter', d.date_day) as date) as qtr,
                            sum(batch_stream_txns) / sum(batch_stream_txns + sweat_relayer_txns + other_txns) as share, count(*) as n
                     from d cross join e where d.date_day <= e.stop_day group by 1
                     having count(*) >= 89)
          select e.first_day, e.last_day, e.stop_day,
                 (select min(qtr) from q) as first_quarter, (select share from q order by qtr limit 1) as first_quarter_share,
                 (select max(qtr) from q) as last_quarter, (select share from q order by qtr desc limit 1) as last_quarter_share,
                 avg(sweat_relayer_txns + other_txns) filter (where d.date_day < e.first_day + 30) as outside_first,
                 avg(sweat_relayer_txns + other_txns) filter (where d.date_day > e.last_day - 30) as outside_now
          from d cross join e group by all""")
        split_check = one(f"""
          select count(*) as days_both, sum(d.batch_stream_txns) / sum(u.batch_stream_txns) - 1 as apart
          from ({unordered(BQ_SPLIT_SQL)}) d join gold.fct_usage_quality_daily u using (date_day)
          where u.batch_stream_txns > 0""")
        bigquery["split"] = {"sql": BQ_SPLIT_SQL, "cols": split_cols,
                             "facts": {**{k: clean(v, 6) for k, v in split_facts.items()},
                                       **{k: clean(v, 6) for k, v in split_check.items()}}}

# WHO CALLS THE CHAIN SIGNATURES CONTRACT, for the Usage page: the last 30 days' function calls to v1.signer by who
# made them. The contract calls itself to finish a request, and its signing nodes call it with their answers, so those
# two are named apart from the accounts that ask for a signature.
BQ_SIG_SQL = f"""-- Who called the Chain Signatures contract over the last 30 days, as NEAR's public BigQuery dataset counts it, for
-- each day's 25 largest callers. The contract's own calls and its signing nodes' calls are named apart from the
-- accounts that ask for a signature; what is left of 100% came from smaller callers.
with total as (
  select sum(contract_calls) as calls
  from (select distinct date_day, contract_calls from gold.fct_bigquery_caller_daily
        where contract_id = 'v1.signer' and {D30})
), nodes as (
  select distinct operator_account_id as account_id from gold.fct_mpc_participants
)
select case when c.is_self_call then 'The contract itself'
            when n.account_id is not null then 'Its signing nodes'
            when c.entity is not null and c.entity not in ('', 'Unlabelled') then c.entity
            else 'Other callers' end as caller_group,
       case when c.is_self_call then 'itself' when n.account_id is not null then 'nodes' else 'asks' end as kind,
       count(distinct c.caller_account_id) as accounts,
       sum(c.calls) as calls,
       sum(c.calls) / (select calls from total) as share
from gold.fct_bigquery_caller_daily c
left join nodes n on n.account_id = c.caller_account_id
where c.contract_id = 'v1.signer' and {D30.replace('date_day', 'c.date_day')}
group by 1, 2
order by 4 desc, 1;"""
if {"fct_bigquery_caller_daily", "fct_mpc_participants"} <= BQ_HAVE:
    sig_rows = table(BQ_SIG_SQL.rstrip(";"), 6)
    sig_days = one(f"""select count(distinct date_day) as n, avg(contract_calls) as calls_a_day, avg(contract_callers) as callers_a_day
                       from (select distinct date_day, contract_calls, contract_callers from gold.fct_bigquery_caller_daily
                             where contract_id = 'v1.signer' and {D30})""")
    if sig_rows and sig_days["n"] == 30:
        bigquery["sigCallers"] = {"sql": BQ_SIG_SQL, "rows": sig_rows,
                                  "facts": {"calls_a_day": clean(sig_days["calls_a_day"], 0), "callers_a_day": clean(sig_days["callers_a_day"], 0)}}

# WHO OWNS THE STAKE, for the Security page: the share of the listed staked NEAR owned by the largest account, the ten
# largest and the hundred largest. The table of staking balances follows more accounts each year, so the days read
# start after the last one on which its list held under 85% of all staked NEAR. The facts set the newest 30 days
# against the first 30, beside the ten largest pools' share of stake in the newest epoch.
BQ_OWNERS_SQL = f"""-- Who owns the staked NEAR, as the table of staking balances in NEAR's public BigQuery dataset lists it: the share
-- of the listed stake owned by the largest account, the ten largest and the hundred largest. An account's stake is
-- its own and its lockup account's. The days start after the last one on which the list held under 85% of all
-- staked NEAR (listed_share_of_stake), because before that it follows too few accounts to stand for the whole.
select date_day, accounts_with_stake, listed_share_of_stake,
       largest_stake_near / listed_stake_near as largest_share,
       top_10_share, top_100_share
from gold.fct_bigquery_staking_balance_daily
where date_day > (select max(date_day) from gold.fct_bigquery_staking_balance_daily
                  where listed_share_of_stake < 0.85)
  and date_day <= {LAST}
order by 1;"""
if {"fct_bigquery_staking_balance_daily", "fct_validator_summary"} <= BQ_HAVE:
    owner_cols = columns(BQ_OWNERS_SQL.rstrip(";"), 6)
    if owner_cols and len(owner_cols["date_day"]) >= 90:
        owner_facts = one(f"""
          with d as ({unordered(BQ_OWNERS_SQL)}),
               e as (select min(date_day) as first_day, max(date_day) as last_day from d)
          select e.first_day, e.last_day,
                 count(*) filter (where d.date_day > e.last_day - 30) as days_now,
                 avg(top_10_share) filter (where d.date_day < e.first_day + 30) as t10_first,
                 avg(top_10_share) filter (where d.date_day > e.last_day - 30) as t10_now,
                 avg(top_100_share) filter (where d.date_day < e.first_day + 30) as t100_first,
                 avg(top_100_share) filter (where d.date_day > e.last_day - 30) as t100_now,
                 avg(largest_share) filter (where d.date_day < e.first_day + 30) as big_first,
                 avg(largest_share) filter (where d.date_day > e.last_day - 30) as big_now,
                 avg(accounts_with_stake) filter (where d.date_day > e.last_day - 30) as holders_now,
                 avg(listed_share_of_stake) filter (where d.date_day > e.last_day - 30) as listed_now
          from d cross join e group by 1, 2""")
        owner_facts["pool_top_10"] = one(f"""
          select top_10_share as v from gold.fct_validator_summary
          where approx_date_day <= {LAST} and is_epoch_complete order by epoch_height desc limit 1""")["v"]
        if owner_facts["days_now"] >= 25:
            bigquery["stakeOwners"] = {"sql": BQ_OWNERS_SQL, "cols": owner_cols,
                                       "facts": {k: clean(v, 6) for k, v in owner_facts.items()}}

# WHETHER THE CHAIN HAS EVER STOPPED, for the Security page. Blocks made on every day since launch, and the accounts
# that produced them. A slow day is read against the median of the 30 days before it. The facts: the days since
# launch and how many of them have a block, the three slowest days, the slowest of the last 365, the block time over
# the newest 30 days and over the same 30 days two years earlier, and the month in which blocks sped up most.
BQ_BLOCKS_SQL = f"""-- Blocks made on each day since launch, as NEAR's public BigQuery dataset counts them, and the accounts that
-- produced a block that day. On a few days the dataset holds some blocks twice, so a day's count is capped at the
-- block heights it spans. usual_blocks is the median of the 30 days before, so blocks / usual_blocks shows a slow
-- day; it is empty for the first 30 days.
with days as (
  select date_day, least(blocks, last_block_height - first_block_height + 1) as blocks, block_producers
  from gold.fct_bigquery_chain_daily
  where is_day_complete and blocks is not null and date_day <= {LAST}
)
select date_day, blocks, block_producers,
       case when row_number() over (order by date_day) > 30
            then median(blocks) over (order by date_day rows between 30 preceding and 1 preceding) end as usual_blocks
from days
order by 1;"""
if "fct_bigquery_chain_daily" in BQ_HAVE:
    block_cols = columns(BQ_BLOCKS_SQL.rstrip(";"), 0)
    if block_cols and len(block_cols["date_day"]) >= 400:
        BLOCK_DAYS = f"({unordered(BQ_BLOCKS_SQL)})"
        block_facts = one(f"""
          with d as {BLOCK_DAYS},
               e as (select min(date_day) as first_day, max(date_day) as last_day from d)
          select e.first_day, e.last_day,
                 datediff('day', e.first_day, e.last_day) + 1 as days,
                 count(*) filter (where blocks > 0) as days_with_blocks,
                 86400 / avg(blocks) filter (where d.date_day > e.last_day - 30) as seconds_now,
                 86400 / avg(blocks) filter (where d.date_day > e.last_day - 760 and d.date_day <= e.last_day - 730) as seconds_two_years_ago,
                 min(block_producers) filter (where d.date_day > e.last_day - 365) as producers_low,
                 max(block_producers) filter (where d.date_day > e.last_day - 365) as producers_high
          from d cross join e group by 1, 2""")
        block_slow = table(f"""
          select date_day, blocks, usual_blocks, blocks / usual_blocks as share_of_usual
          from {BLOCK_DAYS} where usual_blocks is not null
          order by 4, 1 limit 3""", 4)
        block_year = one(f"""
          select date_day, blocks / usual_blocks as share_of_usual
          from {BLOCK_DAYS}
          where usual_blocks is not null and date_day > (select max(date_day) from {BLOCK_DAYS}) - 365
          order by 2, 1 limit 1""")
        block_step = one(f"""
          with m as (select date_trunc('month', date_day) as mth, avg(blocks) as blocks, count(*) as n
                     from {BLOCK_DAYS} group by 1 having count(*) = day(last_day(min(date_day)))),
               r as (select mth, blocks / lag(blocks) over (order by mth) as rise from m)
          select cast(mth as date) as step_month, rise from r where rise is not null order by rise desc, mth limit 1""")
        bigquery["blocks"] = {"sql": BQ_BLOCKS_SQL, "cols": block_cols,
                              "facts": {**{k: clean(v, 4) for k, v in block_facts.items()},
                                        "slow": block_slow,
                                        "year_low_day": clean(block_year["date_day"]),
                                        "year_low_share": clean(block_year["share_of_usual"], 4),
                                        "step_month": clean(block_step["step_month"]),
                                        "step_rise": clean(block_step["rise"], 4)}}

more = {
    "horizon": horizon,
    "rivals": rivals,
    "poolHistory": pool_history,
    "bigquery": bigquery,
    "venearWeeks": venear_weeks,
    "marketDaily": market_daily,
    "oneclickDaily": oneclick_daily,
    "assetGroupsDaily": asset_groups_daily,
    "intentsTvlDaily": intents_tvl_daily,
    "intentsTvlAssets": intents_tvl_assets,
    "intentsRowMonthly": intents_row_monthly,
    "channelDaily": channel_daily,
    "inflowDaily": inflow_daily,
    "receivedDaily": received_daily,
    "pageMonthly": page_monthly,
    "inflowNearDaily": inflow_near_daily,
    "feeLinesDaily": fee_lines_daily,
    "walletEvents": wallet_events,
    "walletDaily": wallet_daily,
    "usageDaily": usage_daily,
    "signerDaily": signer_daily,
    "lstDaily": lst_daily,
    "sizeMonth": size_month,
    "sizeMonths": size_months,
    "walletHeld": wallet_held,
    "locked": locked,
    "signerWeeks": signer_weeks,
    "signerDomains": signer_domains,
    "lstMonths": lst_months,
    "lstNow": lst_now,
    "freshness": freshness,
    "issuanceDaily": issuance_daily,
    "beforeCut": {k: clean(v, 9) for k, v in before_cut[0].items()} if before_cut else None,
    "treasuryDaily": treasury_daily,
    "treasuryOut": treasury_out,
    "yieldDaily": yield_daily,
    "stakingFacts": {k: clean(v, 6) for k, v in staking_facts.items()},
    "stakeMonths": stake_months,
    "supplyMap": {k: clean(v, 0) for k, v in supply_map.items()},
    "foundationReading": {k: clean(v, 0) for k, v in foundation_reading.items()},
    "capital": capital,
    "market": market,
    "etf": {"pool": ETF_POOL, "days": etf_days, "poolDaily": etf_pool, "size": etf_size,
            "facts": {k: clean(v, 9) for k, v in etf_facts.items()}},
    "governance": governance,
    "security": security,
}

# The scorecard on every day (gold.fct_thesis_scorecard_daily), for the base of "The case so far" and the question
# "How steady is the count?". Each tested claim, in the registry's order, as one letter a day (f: the result supports
# the case, a: it counts against it, a full stop: not yet testable) and its values as runs, [first day's index, value],
# because a claim that reads complete months holds one value for a month. Four significant figures are what the page
# prints. The newest day must stand as the scorecard does, or the page would show two counts.
def four_figures(value):
    if value is None:
        return None
    value = float(f"{float(f'{float(value):.14g}'):.4g}")
    return round(value) if abs(value) >= 1000 else value


history_days = [r["d"] for r in rows("select distinct date_day d from gold.fct_thesis_scorecard_daily order by 1")]
history_claims = {}
for claim in scorecard:
    days = rows(f"""select stands, value from gold.fct_thesis_scorecard_daily
                    where claim_id = '{claim["claim_id"]}' order by date_day""")
    if len(days) != len(history_days):
        sys.exit(f"The scorecard's history: {claim['claim_id']} has {len(days)} days, not {len(history_days)}")
    runs = []
    for i, r in enumerate(days):
        value = four_figures(r["value"])
        if not runs or runs[-1][1] != value:
            runs.append([i, value])
    letters = "".join({"for": "f", "against": "a"}.get(r["stands"], ".") for r in days)
    if {"f": "for", "a": "against"}.get(letters[-1]) != claim["stands"]:
        sys.exit(f"The scorecard's history: on its newest day {claim['claim_id']} stands {letters[-1]!r}, "
                 f"but the scorecard has it {claim['stands']}")
    history_claims[claim["claim_id"]] = {"s": letters, "v": runs}
history = {"start": clean(history_days[0]), "end": clean(history_days[-1]), "n": len(history_days), "claims": history_claims}

thesis = {
    "settled": clean(FEE_DAY),
    "marketShare": market_share,
    "oneclickMonth": clean(ONECLICK_MONTH),
    "oneclickMix": oneclick_mix,
    "oneclickSides": oneclick_sides,
    "oneclickCorridors": oneclick_corridors,
    "corridorSame": clean(corridor_same),
    "scorecard": scorecard,
    "open": open_claims,
    "tally": tally,
    "history": history,
    "dilution": dilution,
    # Nine decimals, so a figure the page works out from these rates agrees with the warehouse to the dollar
    "dilutionNow": {k: clean(v, 9) for k, v in dilution_now.items()},
    "scenarios": scenarios,
    "unitEconomics": unit_economics,
    "channelMonths": channel_months,
    "channelPrices": channel_prices,
    "feesToNear": clean(fees_to_near),
    "channelCounts": channel_counts,
    "concentration": concentration,
    "multiples": {"asOf": clean(multiples_day), "latest": multiples_latest, "monthly": multiples_monthly},
    "etfAbsorption": etf_absorption,
}

# Which raw feeds and registry files sit behind each gold table, walked from dbt's own graph.
# The calendar table is skipped, because a date spine says nothing about where the numbers come from.
manifest = json.loads(MANIFEST.read_text())
PREFIX = {"revenue_page": "revenue", "intents_explorer": "explorer", "oneclick": "explorer", "dune_public": "dune", "nrr_fund": "bitwise"}
SEEDS = {"etf_nrr_history": "sosovalue", "dune_queries": "dune"}


def source_id(unique_id):
    name = unique_id.split(".")[-1]
    if unique_id.startswith("seed."):
        return SEEDS.get(name, "registry")
    if name == "rpc__hos_proposals":
        return "hos"
    prefix = name.split("__")[0]
    return PREFIX.get(prefix, prefix)


def roots(node, seen):
    found = set()
    for parent in manifest["parent_map"].get(node, []):
        if parent in seen or parent.endswith(".dim_date"):
            continue
        seen.add(parent)
        if parent.startswith(("source.", "seed.")):
            found.add(source_id(parent))
        else:
            found |= roots(parent, seen)
    return found


gold_nodes = {v["name"]: k for k, v in manifest["nodes"].items() if v["resource_type"] == "model" and v.get("schema", "").endswith("gold")}
lineage_tables = {name: sorted(roots(node, set())) for name, node in sorted(gold_nodes.items())}
terms = {r["source"]: r for r in csv.DictReader((ROOT / "registry" / "sources.csv").open())}
TERMS_ROW = {"revenue": "revenue_page", "explorer": "intents_explorer", "dune": "dune_public", "bitwise": "nrr_fund", "sosovalue": "sosovalue_news"}
feeds = {}
for uid in manifest["sources"]:
    feeds[source_id(uid)] = feeds.get(source_id(uid), 0) + 1
all_ids = sorted({i for ids in lineage_tables.values() for i in ids} | set(feeds))
lineage = {
    "tables": lineage_tables,
    "counts": {"raw": len(manifest["sources"]), "registry": sum(1 for k in manifest["nodes"] if k.startswith("seed.")), "gold": len(gold_nodes)},
    "sources": {i: {"feeds": feeds.get(i, 0), "access": (terms.get(TERMS_ROW.get(i, i)) or {}).get("access", "Reviewed in the repo"), "terms": (terms.get(TERMS_ROW.get(i, i)) or {}).get("terms_url", "")} for i in all_ids},
}

# Two counts `make verify` prints, read from the same places: the raw files listed at fetch time, and the tests dbt runs
bronze_files = sum(1 for path in sorted((ROOT / "data" / "bronze" / "_manifest").glob("dt=*.jsonl")) for line in path.read_text().splitlines() if line)
data_tests = sum(1 for node in manifest["nodes"].values() if node["resource_type"] == "test") + len(manifest.get("unit_tests", {}))

# ---- The days after the settled day ----------------------------------------------------------------------------------
# Seven charts over time are drawn to the newest full day. Their days after the settled day are kept apart here, so
# that no headline figure reads them. The page appends them to those charts, and where a figure can still be revised
# (fees, multiples built on fees, other chains' DEX volume) the chart marks those days.
AFTER = f"date_day > {FEES} and date_day <= {LAST}"
soft = {
    "market": columns(f"""
      with p as (select date_day, sum(dex_volume_usd) as peers from gold.fct_peer_daily
                 where chain_id <> 'near' group by 1)
      select i.date_day as d, i.volume_usd as intents, p.peers
      from gold.fct_intents_daily i join p using (date_day)
      where {AFTER} order by 1""", 0),
    "fees": columns(f"""
      select date_day as d, fees_usd as fee, volume_usd as vol
      from gold.fct_intents_daily where {AFTER} order by 1""", 0),
    "dilution": columns(f"""
      select date_day as d, revenue_inflow_30d_near / nullif(minted_30d_near, 0) as recv,
             burn_30d_near / nullif(minted_30d_near, 0) as burnt
      from gold.fct_net_dilution_daily where {AFTER} order by 1""", 5),
    "yields": columns(f"""
      with y as ({LST_PAID})
      select n.date_day as d, n.nominal_staking_yield_rate as before_fees, y.liquid, n.gross_inflation_rate as issuance
      from gold.fct_net_dilution_daily n left join y using (date_day)
      where n.nominal_staking_yield_rate is not null and {AFTER} order by 1""", 6),
    "multiples": columns(f"""
      select date_day as d, max(multiple) filter (where chain_id = 'near') as near,
             median(multiple) filter (where chain_id <> 'near') as peer
      from gold.fct_valuation_multiples_daily
      where basis = 'app_fees' and date_day > date '{multiples_day}' and date_day <= {LAST}
      group by 1 order by 1""", 4),
    "ninety": columns(f"""
      with inc as (
        select s.date_day, m.market_cap_usd as cap, p.fees_usd,
               s.burn_near * m.price_usd + coalesce(i.usd, 0) as token_usd
        from gold.fct_supply_daily s
        join gold.fct_market_daily m using (date_day)
        left join (select date_day, sum(received_usd) as usd from gold.fct_revenue_inflows_daily group by 1) i using (date_day)
        left join (select date_day, fees_usd from gold.fct_peer_daily where chain_id = 'near') p using (date_day)
        where s.date_day <= {LAST}),
      w as (
        select date_day, cap, sum(fees_usd) over win as fees_90d, sum(token_usd) over win as token_90d,
               count(fees_usd) over win as fee_days, count(token_usd) over win as token_days
        from inc window win as (order by date_day rows between 89 preceding and current row))
      select date_day as d, cap / (fees_90d * 365 / 90) as fees, cap / (token_90d * 365 / 90) as token
      from w
      where fee_days = 90 and token_days = 90 and {AFTER}
      order by 1""", 4),
}

payload = {
    "asOf": clean(LAST_DAY),
    "pinned": (ROOT / "data" / "PINNED").read_text().strip(),
    "windows": {"last": clean(LAST_DAY), "fees": clean(FEE_DAY), "dune": clean(DUNE_DAY), "duneRead": clean(DUNE_READ)},
    "latest": {k: clean(v) for k, v in latest.items()},
    "base30": {k: clean(v) for k, v in base30.items()},
    "intents30": {k: clean(v) for k, v in intents30.items()},
    "intentsAll": {**{k: clean(v) for k, v in intents_all.items()},
                   "volLast": clean(intents_all_last["vol"]), "swapsLast": clean(intents_all_last["swaps"]),
                   "swapsAll": clean(dune_swaps_all["swaps"]), "swapsThrough": clean(dune_swaps_all["through"])},
    "vol30": clean(intents_vol30),
    "price30": clean(price30["p"]),
    "chain30": {k: clean(v) for k, v in chain30.items()},
    "validators": {k: clean(v) for k, v in validators.items()},
    "mpc": mpc,
    "venear": {k: clean(v) for k, v in venear.items()},
    "config": {k: clean(v) for k, v in config.items()},
    "warehouse": {"tables": gold_tables, "columns": gold_columns, "sources": sources, "bronzeFiles": bronze_files, "dataTests": data_tests},
    "reconCounts": recon_counts,
    "weekly": weekly,
    "intentsDaily": intents_daily,
    "intentsWeekly": intents_weekly,
    "revenueMonthly": revenue_monthly,
    "peers": peers,
    "peerFeesWeekly": peer_fees_weekly,
    "recon": recon,
    "outside": outside_counts,
    "channels": channels,
    "channelBucket": channel_bucket[0]["fees_usd"] if channel_bucket else None,
    "chains30": chains_30d,
    "duneChains30": dune_chains_30d,
    "capture": capture,
    "gov": gov,
    "events": events,
    "daily": daily,
    "assets30": assets30,
    "scopes": scopes,
    "validatorsTop": validators_top,
    "stableAssets": stable_assets,
    "confTvl": conf_tvl_col,
    "peerWeekly": peer_weekly,
    "wallet30": wallet30,
    "etf": {"daily": etf_daily, "chain": etf_chain, "checks": etf_checks, "prices": {k: clean(v) for k, v in etf_prices.items()}},
    "lineage": lineage,
    "validatorsDaily": validators_daily,
    "more": more,
    "soft": soft,
    "thesis": thesis,
    "usage": usage,
    "developers": developers,
}

OUT.parent.mkdir(parents=True, exist_ok=True)
OUT.write_text("window.LC = " + json.dumps(payload, separators=(",", ":"), default=str) + ";\n")
print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1024:.0f} KB): data through {payload['asOf']}, "
      f"fees settled through {payload['windows']['fees']}, {len(scorecard)} claims "
      f"({tally['for']} for, {tally['against']} against, {tally['open']} not settled)")
