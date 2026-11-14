-- Derived from NEAR's Intents dashboard on Dune: the value held in NEAR Intents per asset per day, public and
-- confidential balances together (query 7586763, "TVL by Asset", from 2026-01-01, first read on 2026-11-10). The
-- assets add up to fct_dune_intents_tvl_daily on every day. The wNEAR row is the NEAR parked in Intents; divided by the
-- day's price it is within a few percent of intents.near's wNEAR balance on chain (dq_reconciliation). A later reading
-- replaces an earlier one's value for the same day.
with widget as (
    select
        snapshot_date,
        generated_at,
        reading_id,
        cast(row_doc->>'date_at' as date) as date_day,
        row_doc->>'symbol' as symbol,
        cast(row_doc->>'tvl_usd' as double) as tvl_usd
    from {{ ref('stg_dune_public__query_results') }}
    where query_id = 7586763 and is_complete
),

latest as (
    select
        *,
        row_number() over (
            partition by date_day, symbol order by snapshot_date desc, generated_at desc nulls last, reading_id
        ) = 1 as keep
    from widget
)

select
    date_day,
    symbol,
    tvl_usd,
    tvl_usd / nullif(sum(tvl_usd) over (partition by date_day), 0) as share_of_day,
    snapshot_date,
    {{ dune_credit() }} as derived_from
from latest
where keep
