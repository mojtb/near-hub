with files as ({{ bronze_files('revenue_page__parsed') }}),

rows as (
    select snapshot_date, {{ explode("doc->'intentVolumeSeries'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date_at', 10) as date) as date_day,
        cast(r->>'volume_usd' as double) as volume_usd,
        cast(r->>'cumulative_volume_usd' as double) as cumulative_volume_usd,
        cast(r->>'is_stale' as integer) as is_stale
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
