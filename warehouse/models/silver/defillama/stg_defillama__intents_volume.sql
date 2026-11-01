with files as ({{ bronze_files('defillama__intents_volume') }}),

points as (
    select snapshot_date, {{ explode("doc->'totalDataChart'") }} as p from files
),

typed as (
    select
        snapshot_date,
        {{ unix_day("p->>0") }} as date_day,
        cast(p->>1 as double) as volume_usd
    from points
)

select *, {{ is_latest('date_day', 'volume_usd') }} as is_latest
from typed
where date_day < snapshot_date
