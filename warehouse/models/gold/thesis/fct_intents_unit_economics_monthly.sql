-- NEAR's Intents revenue per month, split into the three things that make it: volume, the fee rate charged on it, and
-- the share of those fees NEAR keeps. revenue = volume x fee_rate x capture_rate, so the change from one month to the
-- next splits exactly into three log effects. Days whose fees can still change are left out, so the newest month is short.
with days as (
    select * from {{ ref('fct_intents_daily') }}
    where not is_fee_revenue_provisional and volume_usd is not null
),

months as (
    select
        cast(date_trunc('month', date_day) as date) as month_start,
        count(*) as days_counted,
        count(*) = day(last_day(min(date_day))) as is_month_complete,
        count(fees_usd) = count(*) and count(revenue_usd) = count(*) as has_fees_every_day,
        sum(volume_usd) as volume_usd,
        sum(fees_usd) as fees_usd,
        sum(revenue_usd) as revenue_usd,
        -- Rates use only the days that carry both sides, so a month that starts part-way is not understated.
        sum(fees_usd) / nullif(sum(volume_usd) filter (where fees_usd is not null), 0) as fee_rate,
        sum(revenue_usd) filter (where fees_usd is not null) / nullif(sum(fees_usd) filter (where revenue_usd is not null), 0) as capture_rate,
        sum(revenue_usd) / nullif(sum(volume_usd) filter (where revenue_usd is not null), 0) as net_take_rate,
        -- Two sources, so public volume can read a little above all-route volume; it is capped day by day.
        1 - sum(least(public_volume_usd, volume_usd)) filter (where public_volume_usd is not null)
            / nullif(sum(volume_usd) filter (where public_volume_usd is not null), 0) as confidential_volume_share
    from days
    group by 1
),

-- Per-day means, so a 31-day month and a 30-day month compare fairly.
steps as (
    select
        *,
        lag(month_start) over (order by month_start) as previous_month,
        ln(nullif(volume_usd / days_counted, 0)) as ln_volume,
        ln(nullif(fee_rate, 0)) as ln_fee_rate,
        ln(nullif(capture_rate, 0)) as ln_capture,
        -- The revenue wallets' first two months hold test transfers of a few dollars; a log change from those says nothing.
        is_month_complete and has_fees_every_day and revenue_usd >= 1000 as is_comparable
    from months
),

changes as (
    select
        s.*,
        s.is_comparable and p.is_comparable and s.previous_month = cast(s.month_start - interval 1 month as date) as has_previous,
        p.ln_volume as previous_ln_volume,
        p.ln_fee_rate as previous_ln_fee_rate,
        p.ln_capture as previous_ln_capture
    from steps s
    left join steps p on p.month_start = s.previous_month
)

select
    month_start,
    days_counted,
    is_month_complete,
    volume_usd,
    fees_usd,
    revenue_usd,
    fee_rate,
    capture_rate,
    net_take_rate,
    confidential_volume_share,
    case when has_previous then (ln_volume + ln_fee_rate + ln_capture) - (previous_ln_volume + previous_ln_fee_rate + previous_ln_capture) end as revenue_log_change,
    case when has_previous then ln_volume - previous_ln_volume end as volume_log_effect,
    case when has_previous then ln_fee_rate - previous_ln_fee_rate end as fee_rate_log_effect,
    case when has_previous then ln_capture - previous_ln_capture end as capture_log_effect
from changes
