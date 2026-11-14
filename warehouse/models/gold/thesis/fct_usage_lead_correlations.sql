-- The working hypothesis in the track's sample prompt: "cross-chain volume through NEAR Intents is a better leading
-- indicator of real network usage than token price". Each row is one Pearson correlation between week-on-week log
-- changes: a leader (Intents volume or the NEAR price) against a usage measure, with the leader in the same week or
-- one, two or four weeks ahead of usage.
-- Weeks are blocks of seven days counted from 2026-04-13, and usage changes are read from the second block on, so
-- no change crosses the break of 2026-04-02 or the stop of relay.tg on 2026-04-13 and 14. Only full blocks are
-- read. week_shift_days = 0 cuts the weeks on Mondays, which is the reading the scorecard and the site use; 1 to 6
-- cut the same days one to six days later, to show how far a figure moves with the weekday alone.
-- chance_bound is the largest correlation that chance alone gives 19 times in 20 between two unrelated series of
-- that many weeks (the two-sided 5% bound for Pearson's r; 1.96 + 2.4/df stands in for Student's t).
with shifts as (
    select cast(unnest(range(0, 7)) as integer) as week_shift_days
),

days as (
    select
        c.date_day,
        i.volume_usd,
        m.price_usd,
        u.txns_ex_batch_streams_and_sweat as txns,
        u.other_txns,
        c.distinct_signers,
        c.gas_fee_near
    from {{ ref('fct_chain_daily') }} c
    join {{ ref('fct_usage_quality_daily') }} u using (date_day)
    join {{ ref('fct_intents_daily') }} i using (date_day)
    join {{ ref('fct_market_daily') }} m using (date_day)
    where u.other_txns is not null and c.distinct_signers is not null and c.gas_fee_near is not null
      and i.volume_usd is not null and m.price_usd is not null
),

weeks as (
    select
        s.week_shift_days,
        cast(floor(datediff('day', date '2026-04-13' + s.week_shift_days, d.date_day) / 7.0) as integer) as week_no,
        min(d.date_day) as week_start,
        sum(d.volume_usd) as volume_usd,
        avg(d.price_usd) as price_usd,
        avg(d.txns) as txns,
        avg(d.other_txns) as other_txns,
        avg(d.distinct_signers) as signers,
        avg(d.gas_fee_near) as gas_fee_near
    from days d
    cross join shifts s
    group by 1, 2
    having count(*) = 7
),

-- A change needs the week before it, so a missing week leaves a gap and never a change across two weeks.
changes as (
    select
        w.week_shift_days,
        w.week_no,
        w.week_start,
        ln(w.volume_usd / p.volume_usd) as d_volume,
        ln(w.price_usd / p.price_usd) as d_price,
        ln(w.txns / p.txns) as d_txns,
        ln(w.other_txns / p.other_txns) as d_other,
        ln(w.signers / p.signers) as d_signers,
        ln(w.gas_fee_near / p.gas_fee_near) as d_gas
    from weeks w
    join weeks p on p.week_shift_days = w.week_shift_days and p.week_no = w.week_no - 1
),

leaders as (
    select week_shift_days, week_no, 'intents_volume' as leader, d_volume as d_leader from changes
    union all
    select week_shift_days, week_no, 'near_price', d_price from changes
),

usage as (
    select week_shift_days, week_no, week_start, 'transactions' as usage_measure, d_txns as d_usage from changes where week_no >= 1
    union all
    select week_shift_days, week_no, week_start, 'other_transactions', d_other from changes where week_no >= 1
    union all
    select week_shift_days, week_no, week_start, 'signers', d_signers from changes where week_no >= 1
    union all
    select week_shift_days, week_no, week_start, 'gas_paid', d_gas from changes where week_no >= 1
),

leads as (
    select cast(unnest([0, 1, 2, 4]) as integer) as lead_weeks
)

select
    u.week_shift_days,
    l.leader,
    u.usage_measure,
    k.lead_weeks,
    -- Rounded, because a sum over weeks is not the same to the last digit on every build.
    round(corr(l.d_leader, u.d_usage), 10) as correlation,
    count(*) as weeks,
    (1.96 + 2.4 / (count(*) - 2)) / sqrt((count(*) - 2) + power(1.96 + 2.4 / (count(*) - 2), 2)) as chance_bound,
    min(u.week_start) as first_week,
    max(u.week_start) as last_week
from usage u
cross join leads k
join leaders l on l.week_shift_days = u.week_shift_days and l.week_no = u.week_no - k.lead_weeks
group by 1, 2, 3, 4
