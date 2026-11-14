-- Derived from NEAR's Intents dashboard on Dune: all Intents volume per asset per day, public and confidential
-- together, with both dashboard filters on ALL. Two widgets feed it: the full history (query 5157527, first read on
-- 2026-11-10) and the last 30 days (query 5175131), which is all the first reading holds. A later reading replaces an
-- earlier one's value for the same day, and within one reading the full history is used. Each dollar of a swap is
-- counted once, and the dashboard does not say on which side of the swap. fct_intents_asset_daily is the public-only
-- view from NearBlocks.
with widget as (
    select
        snapshot_date,
        generated_at,
        query_id,
        cast(row_doc->>'date_at' as date) as date_day,
        row_doc->>'symbol' as symbol,
        cast(row_doc->>'volume_usd' as double) as volume_usd
    from {{ ref('stg_dune_public__query_results') }}
    where reading_id in (
        '5157527__blockchain-ALL__symbol-ALL__cols-8c7d29',
        '5175131__blockchain-ALL__symbol-ALL__cols-8c7d29'
    )
),

-- The full history has the lower query id, so it wins a tie within one reading.
latest as (
    select
        *,
        row_number() over (
            partition by date_day, symbol order by snapshot_date desc, generated_at desc nulls last, query_id
        ) = 1 as keep
    from widget
)

select
    date_day,
    symbol,
    volume_usd,
    volume_usd / nullif(sum(volume_usd) over (partition by date_day), 0) as share_of_day,
    snapshot_date,
    {{ dune_credit() }} as derived_from
from latest
where keep
