-- Derived from NEAR's Intents dashboard on Dune: the value held in NEAR Intents per day, split into what sits in
-- public balances and what sits in confidential ones (query 8644298, "TVL by Intents type", first read on 2026-11-10).
-- The two scopes add up to the dashboard's TVL tile, and per asset to fct_dune_intents_tvl_asset_daily. A later
-- reading replaces an earlier one's value for the same day.
with widget as (
    select
        snapshot_date,
        generated_at,
        reading_id,
        cast(row_doc->>'date_at' as date) as date_day,
        row_doc->>'source_type' as scope,
        cast(row_doc->>'tvl_usd' as double) as tvl_usd
    from {{ ref('stg_dune_public__query_results') }}
    where query_id = 8644298 and is_complete
),

latest as (
    select
        *,
        row_number() over (
            partition by date_day, scope order by snapshot_date desc, generated_at desc nulls last, reading_id
        ) = 1 as keep
    from widget
)

select
    date_day,
    scope,
    tvl_usd,
    snapshot_date,
    {{ dune_credit() }} as derived_from
from latest
where keep
