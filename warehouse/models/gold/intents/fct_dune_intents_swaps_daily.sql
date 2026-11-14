-- Derived from NEAR's Intents dashboard on Dune: swaps per day across all routes, public and confidential, and the
-- running total (query 4374089, "NEAR Intents - Activity", first read on 2026-11-10). NearBlocks counts public swaps
-- only (fct_intents_daily.public_swaps), which from 2026-11-03 is a small part of them. A later reading replaces an
-- earlier one's value for the same day.
with widget as (
    select
        snapshot_date,
        generated_at,
        reading_id,
        cast(row_doc->>'date_at' as date) as date_day,
        cast(row_doc->>'total_swaps' as bigint) as swaps,
        cast(row_doc->>'cumulative_swaps' as bigint) as cumulative_swaps
    from {{ ref('stg_dune_public__query_results') }}
    where query_id = 4374089 and is_complete
),

latest as (
    select
        *,
        row_number() over (
            partition by date_day order by snapshot_date desc, generated_at desc nulls last, reading_id
        ) = 1 as keep
    from widget
)

select
    date_day,
    swaps,
    cumulative_swaps,
    snapshot_date,
    {{ dune_credit() }} as derived_from
from latest
where keep
