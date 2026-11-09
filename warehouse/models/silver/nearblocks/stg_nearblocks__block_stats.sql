-- Daily blocks, chunks, shards, gas price, gas used, gas fee and total supply from NearBlocks /v3/block-stats.
-- Gas fee, gas used and total supply equal /v1/charts to the unit on every day both hold, so gold reads them from here
-- first: /v1 is switched off on 2026-11-22. Amounts arrive in yoctoNEAR.
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
        cast(r->>'gas_price' as double) as gas_price_yocto,
        cast(r->>'gas_used' as double) as gas_used,
        {{ yocto_to_near("r->>'gas_fee'") }} as gas_fee_near,
        {{ yocto_to_near("r->>'total_supply'") }} as total_supply_near
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
