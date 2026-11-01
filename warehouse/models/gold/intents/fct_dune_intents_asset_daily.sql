-- Derived from NEAR's Intents dashboard on Dune: all Intents volume per asset per day, public and confidential
-- together, with both dashboard filters on ALL. Each reading covers about 30 days, and a later reading replaces an
-- earlier one's value for the same day. fct_intents_asset_daily is the public-only view from NearBlocks.
with widget as (
    select
        snapshot_date,
        generated_at,
        cast(row_doc->>'date_at' as date) as date_day,
        row_doc->>'symbol' as symbol,
        cast(row_doc->>'volume_usd' as double) as volume_usd
    from {{ ref('stg_dune_public__query_results') }}
    where reading_id = '5175131__blockchain-ALL__symbol-ALL__cols-8c7d29'
),

latest as (
    select *, {{ is_latest('date_day, symbol', 'generated_at') }} as keep from widget
)

select
    date_day,
    symbol,
    volume_usd,
    volume_usd / sum(volume_usd) over (partition by date_day) as share_of_day,
    snapshot_date,
    {{ dune_credit() }} as derived_from
from latest
where keep
