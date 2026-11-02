-- 1Click per UTC day, from the Intents Explorer API. 1Click is one route into NEAR Intents, so the volume here is
-- part of the total in fct_intents_daily. Empty until INTENTS_EXPLORER_JWT is set and a snapshot is in the build.
with channels as (
    select
        date_day,
        sum(swaps) filter (where status = 'SUCCESS') as finished_swaps,
        sum(swaps) filter (where status = 'REFUNDED') as refunded_swaps,
        sum(amount_in_usd) filter (where status = 'SUCCESS') as volume_usd,
        sum(amount_out_usd) filter (where status = 'SUCCESS') as amount_out_usd,
        sum(app_fee_usd) filter (where status = 'SUCCESS') as app_fees_usd
    from {{ ref('stg_intents_explorer__channels') }}
    where is_latest
    group by date_day
)

select
    d.date_day,
    d.swaps,
    c.finished_swaps,
    c.refunded_swaps,
    c.volume_usd,
    c.amount_out_usd,
    c.app_fees_usd,
    d.senders,
    d.recipients,
    c.volume_usd / nullif(i.volume_usd_defillama, 0) as share_of_all_intents_volume
from {{ ref('stg_intents_explorer__days') }} d
join channels c using (date_day)
left join {{ ref('fct_intents_daily') }} i using (date_day)
where d.is_latest
