-- 1Click per UTC day, from the Intents Explorer API. 1Click is one route into NEAR Intents, so the volume here is
-- part of the total in fct_intents_daily. Empty until INTENTS_EXPLORER_JWT is set and a snapshot is in the build.
-- Its share is taken of fct_intents_daily.volume_usd, the all-route total, which has the same scope on every day.
-- History arrives out of order: recent days in full, then one day a week back to the start, then the days between,
-- newest first. Until that walk is finished the table holds an unbroken run of recent days and, before it, scattered days.
-- is_in_daily_run marks the run: it starts on the day after the newest gap (macro oneclick_daily_run_start). A day with
-- no 1Click swap at all leaves no tally and ends the run too. The walk was finished on 2026-11-10, and the only gaps
-- left are ten such days from 2025-04-05 to 2025-05-18, so the run starts on 2025-05-19.
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
    -- The Explorer's rows carry no sender before 2026, and a day with finished swaps cannot have had none.
    nullif(d.senders, 0) as senders,
    d.recipients,
    c.volume_usd / nullif(i.volume_usd, 0) as share_of_all_intents_volume,
    coalesce(d.date_day >= {{ oneclick_daily_run_start() }}, false) as is_in_daily_run
from {{ ref('stg_intents_explorer__days') }} d
join channels c using (date_day)
left join {{ ref('fct_intents_daily') }} i using (date_day)
where d.is_latest
