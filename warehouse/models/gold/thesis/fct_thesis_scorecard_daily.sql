-- The scorecard on every day since 2025-01-01: each tested claim in dim_claim measured as fct_thesis_scorecard
-- measures it, with every input cut at that day. It answers "what would the scorecard have said with the data up to
-- this day", from the warehouse as it stands now; it is not a record of what was read on the day, because sources
-- revise recent days. fct_thesis_scorecard stays the scorecard: this table repeats its tests in a form that takes a
-- day, and the data test thesis_scorecard_daily_ends_on_the_scorecard fails the build if the two differ on the
-- newest day, so a claim cannot be changed in one and forgotten in the other.
-- Two rules go beyond the scorecard's, and neither changes the newest day:
--   1. A window must be whole. A test of three months against three reads six complete months, a three-month test
--      three, and a month counts once its last day has come. Until then the claim is not_yet_testable.
--   2. Where the scorecard reads a figure as it was fetched, an earlier day reads what that fetch would have held:
--      the revenue page's month in progress is counted only on the newest day, and liquid staking's reading from a
--      year earlier is the newest one on or before that day, because readings were monthly before 2025.
with newest as (
    select greatest(
        (select max(date_day) from {{ ref('fct_intents_daily') }}),
        (select max(date_day) from {{ ref('fct_chain_daily') }}),
        (select max(date_day) from {{ ref('fct_circulating_supply_daily') }}),
        (select max(snapshot_date) from {{ ref('fct_lst_snapshot') }})
    ) as d
),

-- 2025-01-01 is the first day fct_validator_summary has a complete epoch; NEAR Intents itself began in December 2024.
spine as (
    select cast(unnest(generate_series(date '2025-01-01', (select d from newest), interval 1 day)) as date) as d
),

-- The newest day whose Intents fees are settled, as of each day.
settled as (
    select s.d, max(i.date_day) as sd
    from spine s
    join {{ ref('fct_intents_daily') }} i on i.date_day <= s.d and not i.is_fee_revenue_provisional
    group by 1
),

-- Complete months of Intents, newest first, as of each day.
months as (
    select s.d, m.month_start, m.volume_usd, m.fees_usd, m.revenue_usd,
        row_number() over (partition by s.d order by m.month_start desc) as recency
    from spine s
    join {{ ref('fct_intents_unit_economics_monthly') }} m on m.is_month_complete and last_day(m.month_start) <= s.d
),

peer_dex_monthly as (
    select cast(date_trunc('month', date_day) as date) as month_start, sum(dex_volume_usd) as dex_volume_usd
    from {{ ref('fct_peer_daily') }}
    where chain_id <> 'near'
    group by 1
),

-- The last three complete months, and the three before them.
quarters as (
    select
        m.d,
        m.recency <= 3 as is_newest,
        count(*) as n_months,
        sum(m.volume_usd) as volume_usd,
        sum(m.fees_usd) as fees_usd,
        sum(m.revenue_usd) as revenue_usd,
        sum(p.dex_volume_usd) as peer_dex_volume_usd,
        max(m.month_start) as last_month
    from months m
    join peer_dex_monthly p using (month_start)
    where m.recency <= 6
    group by 1, 2
),

-- One row for each day that has both quarters whole.
q as (
    select a.d, a.last_month,
        a.volume_usd as volume_a, a.peer_dex_volume_usd as peer_a, a.fees_usd as fees_a, a.revenue_usd as revenue_a,
        b.volume_usd as volume_b, b.peer_dex_volume_usd as peer_b, b.fees_usd as fees_b, b.revenue_usd as revenue_b
    from quarters a
    join quarters b on b.d = a.d and a.is_newest and not b.is_newest
    where a.n_months = 3 and b.n_months = 3
),

-- The months in which the 1Click daily run has every day, newest first, as of each day.
oneclick_months as (
    select s.d, o.month_start, row_number() over (partition by s.d order by o.month_start desc) as recency
    from spine s
    join (select distinct month_start from {{ ref('fct_intents_channel_economics_monthly') }} where is_month_complete) o
        on last_day(o.month_start) <= s.d
),

oneclick_whole as (
    select d, count(*) as n_months, last_day(max(month_start)) as end_day from oneclick_months group by 1
),

channels as (
    select o.d, c.referral, c.app_fee_usd, o.recency
    from {{ ref('fct_intents_channel_economics_monthly') }} c
    join oneclick_months o using (month_start)
    where o.recency <= 6
),

partner_fees as (
    select d, referral, sum(app_fee_usd) as app_fee_usd from channels where recency <= 3 group by 1, 2
),

-- 1Click volume by month, with and without Zcash on one side, so a day reads three rows and not three months of pairs.
zec_monthly as (
    select cast(date_trunc('month', date_day) as date) as month_start,
        sum(amount_in_usd) filter (where origin_symbol = 'ZEC' or destination_symbol = 'ZEC') as zec_usd,
        sum(amount_in_usd) as all_usd
    from {{ ref('fct_intents_1click_pair_daily') }}
    where is_in_daily_run
    group by 1
),

-- Three 30-day readings, 30 days apart, add up to 90 days: the newest 90 and the 90 before them.
offset_90d as (
    select
        st.d,
        k.k < 3 as is_newest,
        count(*) as n_readings,
        sum(n.burn_30d_near + n.revenue_inflow_30d_near) / sum(n.minted_30d_near) as offset_share
    from settled st
    cross join (select unnest(range(0, 6)) as k) k
    join {{ ref('fct_net_dilution_daily') }} n on n.date_day = st.sd - cast(k.k * 30 as integer)
    group by 1, 2
),

-- Application fees by chain and month, then the change from one quarter to the next as of each day.
peer_fees_monthly as (
    select chain_id, cast(date_trunc('month', date_day) as date) as month_start, sum(fees_usd) as fees_usd
    from {{ ref('fct_peer_daily') }}
    group by 1, 2
),

fees_quarters as (
    select
        q.d,
        p.chain_id,
        sum(p.fees_usd) filter (where p.month_start >= q.last_month - interval 2 month)
            / sum(p.fees_usd) filter (where p.month_start < q.last_month - interval 2 month) - 1 as fee_change
    from q
    join peer_fees_monthly p on p.month_start >= q.last_month - interval 5 month and p.month_start <= q.last_month
    group by 1, 2
),

-- The newest day NEAR has a settled multiple on application fees, as of each day.
multiple_day as (
    select s.d, max(m.date_day) as md
    from spine s
    join {{ ref('fct_valuation_multiples_daily') }} m
        on m.date_day <= s.d and m.basis = 'app_fees' and m.chain_id = 'near' and not m.is_provisional
    group by 1
),

signers as (
    select date_day, distinct_signers from {{ ref('fct_chain_daily') }} where distinct_signers is not null
),

signers_end as (
    select s.d, max(g.date_day) as e from spine s join signers g on g.date_day <= s.d group by 1
),

revenue_wallets as (select distinct account_id from {{ ref('fct_revenue_inflows_daily') }}),

-- What the Intents contract paid the revenue wallets, a day at a time: native USDC at one dollar, NEAR at the transfer's value.
wallet_receipts as (
    select t.date_day,
        sum(case when t.asset_id = 'nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1'
                 then t.amount_token else t.amount_usd end) as paid_usd
    from {{ ref('fct_wallet_transfers') }} t
    where t.account_id in (select account_id from revenue_wallets) and t.direction = 'in'
      and t.counterparty_id = 'intents.near'
      and t.asset_id in ('native:near', 'nep141:wrap.near',
                         'nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1')
    group by 1
),

-- revenue.near.org's monthly series is read whole, with the month in progress as it stood at the fetch. That month
-- runs to the newest day, so only the newest day may count it; an earlier day reads the months that had ended, and
-- the transfers to the end of the last of them.
revenue_cut as (
    select s.d,
        s.d >= (select d from newest) as is_newest,
        case when s.d >= (select d from newest) or last_day(s.d) = s.d then s.d
             else cast(date_trunc('month', s.d) - interval 1 day as date) end as cut
    from spine s
),

revenue_paid as (
    select c.d, sum(w.paid_usd) as paid_usd
    from revenue_cut c join wallet_receipts w on w.date_day <= c.cut
    group by 1
),

revenue_booked as (
    select c.d, sum(p.revenue_usd) as booked_usd
    from revenue_cut c
    join {{ ref('fct_revenue_page_monthly') }} p
        on (c.is_newest and p.month_start <= c.d) or (not c.is_newest and last_day(p.month_start) <= c.cut)
    group by 1
),

wallets_received as (
    select s.d, sum(i.received_near) as received_near, max(i.date_day) as e
    from spine s join {{ ref('fct_revenue_inflows_daily') }} i on i.date_day <= s.d
    group by 1
),

wallets_sent as (
    select s.d, -sum(f.amount_token) as sent_near
    from spine s
    join {{ ref('fct_wallet_flows_daily') }} f
        on f.date_day <= s.d and f.direction = 'out' and not f.is_between_revenue_wallets
       and f.asset_id in ('native:near', 'nep141:wrap.near')
       and f.account_id in (select account_id from revenue_wallets)
    group by 1
),

etf_day as (
    select s.d, max(e.date_day) as ed from spine s join {{ ref('fct_etf_absorption_daily') }} e on e.date_day <= s.d group by 1
),

supply_day as (
    select s.d, max(c.date_day) as cd from spine s join {{ ref('fct_circulating_supply_daily') }} c on c.date_day <= s.d group by 1
),

-- fct_deflation_scenarios, scenario hsp029_end_state at the measured share of fees, worked out on the settled day
-- of each day: the 30 days of Intents to that day, that day's issuance, burn and price.
scenario_intents as (
    select st.d,
        avg(i.volume_usd) as volume_usd_per_day,
        sum(i.fees_usd) / sum(i.volume_usd) as fee_rate,
        sum(i.revenue_usd) / sum(i.fees_usd) as capture_rate
    from settled st
    join {{ ref('fct_intents_daily') }} i on i.date_day > st.sd - 30 and i.date_day <= st.sd
    group by 1
),

scenario as (
    select st.d, st.sd,
        r.annual_issuance_rate * (n.minted_30d_near * 365 / 30 / n.gross_inflation_rate) / 365 as issuance_near_per_day,
        n.burn_30d_near / 30 as burn_near_per_day,
        m.price_usd, x.fee_rate, x.capture_rate, x.volume_usd_per_day
    from settled st
    join {{ ref('fct_net_dilution_daily') }} n on n.date_day = st.sd
    join {{ ref('fct_market_daily') }} m on m.date_day = st.sd
    join scenario_intents x on x.d = st.d
    cross join (select annual_issuance_rate from {{ ref('issuance_scenarios') }} where scenario_id = 'hsp029_end_state') r
),

validators as (
    select epoch_height, approx_date_day, top_10_share
    from {{ ref('fct_validator_summary') }}
    where is_epoch_complete and approx_date_day is not null
),

validator_epoch as (
    select s.d, max(v.epoch_height) as epoch_height from spine s join validators v on v.approx_date_day <= s.d group by 1
),

-- NEAR staked through the liquid staking tokens, by reading. A reading shows the first block of its day.
liquid_staking as (
    select snapshot_date, sum(delegated_near) as near_staked from {{ ref('fct_lst_snapshot') }} group by 1
),

liquid_staking_end as (
    select s.d, max(l.snapshot_date) as e from spine s join liquid_staking l on l.snapshot_date <= s.d group by 1
),

liquid_staking_year as (
    select x.d, max(l.snapshot_date) as y
    from liquid_staking_end x
    join liquid_staking l on l.snapshot_date <= x.e - interval 365 day and l.snapshot_date > x.e - interval 396 day
    group by 1
),

-- Dollar-pegged tokens held in NEAR Intents, in the months that have every day, newest first, as of each day.
intents_dollar_days as (
    select date_day, sum(tvl_usd) as usd
    from {{ ref('fct_dune_intents_tvl_asset_daily') }}
    where upper(symbol) in ('USDC', 'USDT', 'USDT0', 'USDCX', 'DAI', 'USDG', 'USAD', 'FRAX', 'USD1', 'USDE', 'PYUSD', 'USDS', 'USDF')
    group by 1
),

intents_dollar_months as (
    select s.d, m.month_start, m.mean_usd, row_number() over (partition by s.d order by m.month_start desc) as recency
    from spine s
    join (
        select cast(date_trunc('month', date_day) as date) as month_start, avg(usd) as mean_usd
        from intents_dollar_days
        group by 1
        having count(*) = day(last_day(min(date_day)))
    ) m on last_day(m.month_start) <= s.d
),

-- Transactions on the chain and those sent to intents.near by month, as NEAR's public BigQuery dataset counts them.
-- The dataset is read for each day's 25 largest receivers, so months count from the first in which intents.near was
-- among them on every day; from then on a day without it counts as none. Whole months, newest first, as of each day.
bigquery_month_rows as (
    select
        cast(date_trunc('month', c.date_day) as date) as month_start,
        sum(c.txns) as txns,
        sum(coalesce(r.txns, 0)) as intents_txns,
        count(*) as days,
        count(r.date_day) as intents_days
    from {{ ref('fct_bigquery_chain_daily') }} c
    left join {{ ref('fct_bigquery_receiver_daily') }} r
        on r.date_day = c.date_day and r.receiver_account_id = 'intents.near'
    where c.is_day_complete and c.txns is not null
    group by 1
),

bigquery_months as (
    select s.d, m.month_start, m.txns, m.intents_txns,
        row_number() over (partition by s.d order by m.month_start desc) as recency
    from spine s
    join bigquery_month_rows m on last_day(m.month_start) <= s.d
    where m.days = day(last_day(m.month_start))
      and m.month_start >= (select min(month_start) from bigquery_month_rows where intents_days = day(last_day(month_start)))
),

-- Each claim's measurement on each day, named by its claim_id. no_value_fails marks the one case where a test has
-- an answer without a number: no fee reached the wallets in the 30 days, so no multiple of volume would do.
measured as (
    select d, 'intents_is_gaining_share' as claim_id,
        (volume_a / peer_a) / (volume_b / peer_b) - 1 as value, last_day(last_month) as as_of_date, false as no_value_fails
    from q

    union all
    select d, 'volume_stayed_above_2bn_a_month', min(volume_usd), last_day(max(month_start)), false
    from months where recency <= 3 group by 1 having count(*) = 3

    union all
    select d, 'capture_is_rising', revenue_a / fees_a - revenue_b / fees_b, last_day(last_month), false from q

    union all
    select c.d, 'fee_base_is_widening',
        count(*) filter (where c.recency <= 3) / nullif(count(*) filter (where c.recency > 3), 0)::double - 1,
        max(w.end_day), false
    from channels c
    join oneclick_whole w on w.d = c.d and w.n_months >= 6
    where c.app_fee_usd >= 10000 and c.referral <> '(none)'
    group by 1

    union all
    select c.d, 'revenue_reaches_the_wallets', 1 - coalesce(p.paid_usd, 0) / b.booked_usd,
        (select max(i.date_day) from {{ ref('fct_revenue_inflows_daily') }} i where i.date_day <= c.cut), false
    from revenue_cut c
    join revenue_booked b on b.d = c.d
    left join revenue_paid p on p.d = c.d

    union all
    select r.d, 'revenue_wallets_keep_their_near', coalesce(s.sent_near, 0) / r.received_near, r.e, false
    from wallets_received r
    left join wallets_sent s on s.d = r.d

    union all
    select x.d, 'etf_took_in_more_than_issuance', e.flow_to_issuance_30d_ratio, x.ed, false
    from etf_day x join {{ ref('fct_etf_absorption_daily') }} e on e.date_day = x.ed

    union all
    select a.d, 'offsets_are_rising', a.offset_share - b.offset_share, st.sd, false
    from offset_90d a
    join offset_90d b on b.d = a.d and a.is_newest and not b.is_newest
    join settled st on st.d = a.d
    where a.n_readings = 3 and b.n_readings = 3

    union all
    select x.d, 'unlocks_are_behind', 1 - c.circulating_share_of_total, x.cd, false
    from supply_day x join {{ ref('fct_circulating_supply_daily') }} c on c.date_day = x.cd

    union all
    select d, 'a_doubling_of_volume_reaches_deflation_after_the_cut',
        case when capture_rate > 0
             then (issuance_near_per_day - burn_near_per_day) * price_usd / (fee_rate * capture_rate) / volume_usd_per_day end,
        sd, capture_rate = 0
    from scenario

    union all
    select d, 'near_fees_outgrew_the_median_peer',
        max(fee_change) filter (where chain_id = 'near') - median(fee_change) filter (where chain_id <> 'near'),
        last_day(max(last_month)), false
    from fees_quarters join q using (d)
    group by 1

    union all
    select x.d, 'near_is_dearer_than_the_median_peer',
        max(m.multiple) filter (where m.chain_id = 'near') / median(m.multiple) filter (where m.chain_id <> 'near'),
        x.md, false
    from multiple_day x
    join {{ ref('fct_valuation_multiples_daily') }} m on m.basis = 'app_fees' and m.date_day = x.md
    group by x.d, x.md

    union all
    select p.d, 'fees_depend_on_one_partner', max(p.app_fee_usd) / sum(p.app_fee_usd), max(w.end_day), false
    from partner_fees p
    join oneclick_whole w on w.d = p.d and w.n_months >= 3
    group by 1

    union all
    select o.d, 'zcash_is_on_a_fifth_of_volume', coalesce(sum(z.zec_usd), 0) / sum(z.all_usd), max(w.end_day), false
    from oneclick_months o
    join zec_monthly z using (month_start)
    join oneclick_whole w on w.d = o.d and w.n_months >= 3
    where o.recency <= 3
    group by 1

    union all
    select x.d, 'usage_is_falling',
        avg(g.distinct_signers) filter (where g.date_day > x.e - 30)
            / avg(g.distinct_signers) filter (where g.date_day <= x.e - 180 and g.date_day > x.e - 210) - 1,
        x.e, false
    from signers_end x
    join signers g on g.date_day > x.e - 210 and g.date_day <= x.e
    group by x.d, x.e

    union all
    select d, 'intents_share_of_transactions_is_rising',
        sum(intents_txns) filter (where recency <= 3) / sum(txns) filter (where recency <= 3)
            - sum(intents_txns) filter (where recency between 4 and 6) / sum(txns) filter (where recency between 4 and 6),
        last_day(max(month_start)), false
    from bigquery_months
    where recency <= 6
    group by 1
    having count(*) = 6

    union all
    select x.d, 'ten_pools_hold_a_third', v.top_10_share, v.approx_date_day, false
    from validator_epoch x join validators v on v.epoch_height = x.epoch_height

    union all
    select x.d, 'liquid_staking_is_shrinking', n.near_staked / y.near_staked - 1, x.e, false
    from liquid_staking_end x
    join liquid_staking n on n.snapshot_date = x.e
    join liquid_staking_year yy on yy.d = x.d
    join liquid_staking y on y.snapshot_date = yy.y

    union all
    select d, 'dollars_are_arriving_in_intents',
        avg(mean_usd) filter (where recency <= 3) / avg(mean_usd) filter (where recency between 4 and 6) - 1,
        last_day(max(month_start)), false
    from intents_dollar_months
    where recency <= 6
    group by 1
    having count(*) = 6
),

-- Rounded to ten decimals, as the scorecard rounds, so a rebuild gives the file that was committed. A correlation of
-- a series that did not move is not a number, and counts as no measurement.
rounded as (
    select d, claim_id, case when isnan(value) or isinf(value) then null else round(value, 10) end as value, as_of_date,
        coalesce(no_value_fails, false) as no_value_fails
    from measured
)

select
    s.d as date_day,
    c.claim_id,
    c.side,
    m.value,
    case
        when m.no_value_fails then 'fails'
        when m.value is null then 'not_yet_testable'
        when c.comparison = '>=' and m.value >= c.threshold then 'holds'
        when c.comparison = '<=' and m.value <= c.threshold then 'holds'
        else 'fails'
    end as status,
    case
        when m.no_value_fails then (case when c.side = 'bull' then 'against' else 'for' end)
        when m.value is null then null
        when (c.side = 'bull') = ((c.comparison = '>=' and m.value >= c.threshold) or (c.comparison = '<=' and m.value <= c.threshold)) then 'for'
        else 'against'
    end as stands,
    m.as_of_date
from spine s
cross join {{ ref('dim_claim') }} c
left join rounded m on m.d = s.d and m.claim_id = c.claim_id
where c.comparison is not null
