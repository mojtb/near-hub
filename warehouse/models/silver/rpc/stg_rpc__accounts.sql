with files as ({{ bronze_files('rpc__accounts') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as a from files
)

select
    snapshot_date,
    a->>'account_id' as account_id,
    cast(a->>'exists' as boolean) as account_exists,
    a->>'error' as error_name,
    a->>'amount' as balance_raw,
    {{ yocto_to_near("a->>'amount'") }} as balance_near,
    {{ yocto_to_near("a->>'locked'") }} as staked_near,
    cast(a->>'storage_usage' as bigint) as storage_bytes,
    a->>'code_hash' as code_hash,
    coalesce(a->>'code_hash', '11111111111111111111111111111111') <> '11111111111111111111111111111111' as has_contract,
    cast(a->>'block_height' as bigint) as block_height,
    {{ is_latest("a->>'account_id'") }} as is_latest
from rows
