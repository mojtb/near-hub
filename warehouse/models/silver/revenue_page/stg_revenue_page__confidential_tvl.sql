with files as ({{ bronze_files('revenue_page__parsed') }}),

rows as (
    select snapshot_date, {{ explode("doc->'tvlChartSeries'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'value' as double) as confidential_tvl_usd
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
