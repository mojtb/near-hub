with files as ({{ bronze_files('defillama__protocol_tvl') }}),

points as (
    select snapshot_date, file_key as protocol_slug, {{ explode("doc->'near_tvl'") }} as p from files
),

typed as (
    select
        snapshot_date,
        protocol_slug,
        {{ unix_day("p->>'date'") }} as date_day,
        cast(p->>'totalLiquidityUSD' as double) as tvl_usd
    from points
)

select *, {{ is_latest('protocol_slug, date_day', 'tvl_usd') }} as is_latest
from typed
where date_day < snapshot_date
