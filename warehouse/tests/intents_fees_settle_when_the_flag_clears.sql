-- Holds fct_intents_daily.is_fee_revenue_provisional to the snapshots. Each row returned is a way the flag is wrong:
--   moved_after_flag_cleared: a figure read at least intents_fee_settle_nights nights after its day ended later moved
--     by over 0.01%, the tolerance dq_revisions uses. The sources now settle later than was measured, so measure
--     again and raise the var in dbt_project.yml.
--   flag_disagrees_with_reads: the flag is not what the newest read of each series implies.
-- Each read is compared with the one before it, so a move across a gap in the snapshots counts only if the older read
-- was already past the window. Smaller moves are ignored: the page's floats jitter on every read.
-- Only a day's first week counts. A later move is a rewrite of history, not settling: no trailing flag could predict
-- it, dq_revisions lists it, and because silver keeps every snapshot it would otherwise fail this test for good.
{% set settle_nights = var('intents_fee_settle_nights') %}

with reads as (
    select 'revenue_page fees_usd' as series, date_day, snapshot_date, fees_usd as value
    from {{ ref('stg_revenue_page__fees_daily') }}
    union all
    select 'revenue_page total_fees_near', date_day, snapshot_date, total_fees_near
    from {{ ref('stg_revenue_page__fees_daily') }}
    union all
    select 'defillama ' || data_type, date_day, snapshot_date, value_usd
    from {{ ref('stg_defillama__intents_fees') }}
),

rereads as (
    select
        *,
        lag(snapshot_date) over reads_of_a_day as previous_snapshot,
        lag(value) over reads_of_a_day as previous_value
    from reads
    window reads_of_a_day as (partition by series, date_day order by snapshot_date)
),

implied as (
    select date_day, bool_or(newest_read - date_day < {{ settle_nights }}) as is_provisional
    from (select series, date_day, max(snapshot_date) as newest_read from reads group by series, date_day)
    group by date_day
)

select 'moved_after_flag_cleared' as failure, series, date_day, previous_snapshot, snapshot_date, previous_value, value
from rereads
where previous_snapshot - date_day >= {{ settle_nights }}
  and previous_snapshot - date_day < 7
  and abs(value - previous_value) > 0.0001 * greatest(abs(value), abs(previous_value))

union all

select 'flag_disagrees_with_reads', null, f.date_day, null, null, null, null
from {{ ref('fct_intents_daily') }} f
left join implied i using (date_day)
where f.is_fee_revenue_provisional is distinct from coalesce(i.is_provisional, false)
