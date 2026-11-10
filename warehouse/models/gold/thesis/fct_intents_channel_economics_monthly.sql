-- What each 1Click distribution channel brought in per month: finished volume, the app fees charged on it, the fee
-- rate that implies, and the channel's share of the month. 1Click is one part of NEAR Intents (see
-- fct_intents_1click_daily.share_of_all_intents_volume), and only the unbroken daily run is used.
with rows_in_run as (
    select * from {{ ref('fct_intents_1click_channel_daily') }} where is_in_daily_run
),

run_days as (
    select cast(date_trunc('month', date_day) as date) as month_start, count(distinct date_day) as days_counted
    from rows_in_run
    group by 1
),

channels as (
    select
        cast(date_trunc('month', date_day) as date) as month_start,
        referral,
        coalesce(sum(swaps) filter (where status = 'SUCCESS'), 0) as finished_swaps,
        coalesce(sum(swaps) filter (where status = 'REFUNDED'), 0) as refunded_swaps,
        coalesce(sum(amount_in_usd) filter (where status = 'SUCCESS'), 0) as volume_usd,
        coalesce(sum(app_fee_usd) filter (where status = 'SUCCESS'), 0) as app_fee_usd
    from rows_in_run
    group by 1, 2
)

select
    c.month_start,
    c.referral,
    d.days_counted = day(last_day(c.month_start)) as is_month_complete,
    c.finished_swaps,
    c.refunded_swaps,
    c.refunded_swaps / nullif(c.finished_swaps + c.refunded_swaps, 0) as refunded_share,
    c.volume_usd,
    c.app_fee_usd,
    c.app_fee_usd / nullif(c.volume_usd, 0) as app_fee_rate,
    c.volume_usd / nullif(sum(c.volume_usd) over (partition by c.month_start), 0) as share_of_volume,
    c.app_fee_usd / nullif(sum(c.app_fee_usd) over (partition by c.month_start), 0) as share_of_fees,
    row_number() over (partition by c.month_start order by c.app_fee_usd desc, c.volume_usd desc, c.referral) as fee_rank
from channels c
join run_days d using (month_start)
where c.finished_swaps + c.refunded_swaps > 0
