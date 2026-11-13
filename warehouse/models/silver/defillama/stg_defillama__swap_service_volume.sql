-- Daily volume of each other cross-chain swap service in registry/swap_services.csv, as DefiLlama serves it.
-- file_key is the DefiLlama list asked and the slug, joined by two underscores. llama_id is the id in the reply, which
-- stays the same when a slug changes, so gold joins on it. What a figure counts depends on the list: `dexs` is swaps the
-- service settled, `bridges` is what was sent into it on one chain to arrive on another, each transfer counted once.
with files as ({{ bronze_files('defillama__swap_service_volume') }}),

points as (
    select
        snapshot_date,
        split_part(file_key, '__', 1) as llama_dimension,
        doc->>'defillamaId' as llama_id,
        doc->>'slug' as llama_slug,
        doc->>'name' as protocol_name,
        {{ explode("doc->'totalDataChart'") }} as p
    from files
),

typed as (
    select
        snapshot_date,
        llama_dimension,
        llama_id,
        llama_slug,
        protocol_name,
        {{ unix_day("p->>0") }} as date_day,
        cast(p->>1 as double) as volume_usd
    from points
)

select *, {{ is_latest('llama_dimension, llama_id, date_day', 'volume_usd') }} as is_latest
from typed
where date_day < snapshot_date
