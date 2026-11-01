-- Point in time: one row per stablecoin, chain and snapshot.
with files as ({{ bronze_files('defillama__stablecoin_assets') }}),

assets as (
    select snapshot_date, {{ explode('doc') }} as a from files
),

per_chain as (
    select
        snapshot_date,
        a->>'symbol' as symbol,
        a->>'name' as asset_name,
        a->>'pegType' as peg_type,
        a->'chainCirculating' as circulating,
        unnest(json_keys(a->'chainCirculating')) as llama_chain
    from assets
)

select
    snapshot_date,
    symbol,
    asset_name,
    peg_type,
    llama_chain,
    cast(json_extract_string(circulating, '$."' || llama_chain || '".current.' || peg_type) as double) as circulating,
    {{ is_latest("symbol, asset_name, llama_chain") }} as is_latest
from per_chain
