-- One block per UTC day (within 120 s after 00:00): the on-chain record of supply, gas price and version.
with files as ({{ bronze_files('rpc__block_day') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(r->>'day' as date) as date_day,
        cast(r->>'height' as bigint) as block_height,
        r->>'hash' as block_hash,
        cast(r->>'timestamp' as hugeint) as block_timestamp_ns,
        {{ yocto_to_near("r->>'total_supply'") }} as total_supply_near,
        cast(r->>'gas_price' as hugeint) as gas_price_yocto,
        r->>'epoch_id' as epoch_id,
        cast(r->>'protocol_version' as integer) as protocol_version
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
