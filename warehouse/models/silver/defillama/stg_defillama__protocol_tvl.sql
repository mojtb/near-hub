-- is_latest goes by DefiLlama's id, so a day read under an old slug gives way to the same day read under the new one.
with files as ({{ bronze_files('defillama__protocol_tvl') }}),

points as (
    select snapshot_date, doc->>'id' as protocol_id, file_key as protocol_slug, {{ explode("doc->'near_tvl'") }} as p from files
),

typed as (
    select
        snapshot_date,
        protocol_id,
        protocol_slug,
        {{ unix_day("p->>'date'") }} as date_day,
        cast(p->>'totalLiquidityUSD' as double) as tvl_usd
    from points
)

select *, {{ is_latest('protocol_id, date_day', 'tvl_usd') }} as is_latest
from typed
where date_day < snapshot_date
