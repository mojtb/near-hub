-- The per-protocol summary inside each chain's fee response. Point in time, so one row per snapshot.
with files as ({{ bronze_files('defillama__chain_fees') }}),

rows as (
    select
        snapshot_date,
        split_part(file_key, '__', 1) as llama_chain,
        coalesce(nullif(split_part(file_key, '__', 2), ''), 'dailyFees') as data_type,
        {{ explode("doc->'protocols'") }} as p
    from files
)

select
    snapshot_date,
    llama_chain,
    data_type,
    p->>'name' as protocol_name,
    p->>'slug' as protocol_slug,
    p->>'category' as category,
    cast(p->>'total24h' as double) as total_24h_usd,
    cast(p->>'total7d' as double) as total_7d_usd,
    cast(p->>'total30d' as double) as total_30d_usd,
    cast(p->>'total1y' as double) as total_1y_usd,
    cast(p->>'totalAllTime' as double) as total_all_time_usd,
    {{ is_latest("llama_chain, data_type, p->>'name'") }} as is_latest
from rows
