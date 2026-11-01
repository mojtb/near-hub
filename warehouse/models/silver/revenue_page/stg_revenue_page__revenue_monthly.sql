with files as ({{ bronze_files('revenue_page__parsed') }}),

rows as (
    select snapshot_date, {{ explode("doc->'revenueSeries'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'period_month', 10) as date) as month_start,
        cast(r->>'revenue_usd' as double) as revenue_usd,
        cast(r->>'revenue_near' as double) as revenue_near,
        cast(r->>'cumulative_revenue_usd' as double) as cumulative_revenue_usd,
        cast(r->>'cumulative_revenue_near' as double) as cumulative_revenue_near,
        cast(r->>'is_stale' as integer) as is_stale
    from rows
)

select *, {{ is_latest('month_start') }} as is_latest
from typed
