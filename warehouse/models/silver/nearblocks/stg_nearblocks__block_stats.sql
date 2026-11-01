-- Daily blocks, chunks, gas price and shard count. Also carries gas_fee and total_supply, which are read from v1 instead.
with files as ({{ bronze_files('nearblocks__block_stats') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'blocks' as bigint) as blocks,
        cast(r->>'chunks' as bigint) as chunks,
        cast(r->>'shards' as integer) as shards,
        cast(r->>'gas_price' as double) as gas_price_yocto
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
