-- One row per lockup contract per snapshot that changed it, with its schedule from the contract's stored state. A lockup is
-- known only by its place in lockup.near's order; owners, staking pools and account names are never saved.
with files as ({{ bronze_files('rpc__lockups') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as r from files where file_key = 'schedules'
)

select
    snapshot_date,
    cast(r->>'lockup_no' as integer) as lockup_no,
    r->>'status' as status,
    cast(r->>'created_height' as bigint) as created_height,
    cast(r->>'created_ns' as double) as created_ns,
    cast(r->>'first_read_height' as bigint) as first_read_height,
    r->>'code_hash' as code_hash,
    {{ yocto_to_near("r->>'lockup_amount'") }} as lockup_amount_near,
    coalesce({{ yocto_to_near("r->>'withdrawn'") }}, 0) as first_withdrawn_near,
    cast(r->>'lockup_duration_ns' as double) as lockup_duration_ns,
    cast(r->>'release_duration_ns' as double) as release_duration_ns,
    cast(r->>'lockup_timestamp_ns' as double) as lockup_timestamp_ns,
    cast(r->>'transfers_enabled' as boolean) as transfers_enabled,
    r->>'vesting_kind' as first_vesting_kind,
    cast(r->>'vesting_start_ns' as double) as vesting_start_ns,
    cast(r->>'vesting_cliff_ns' as double) as vesting_cliff_ns,
    cast(r->>'vesting_end_ns' as double) as vesting_end_ns,
    coalesce({{ yocto_to_near("r->>'unvested'") }}, 0) as first_unvested_near,
    r->>'last_vesting_kind' as last_vesting_kind,
    coalesce({{ yocto_to_near("r->>'last_withdrawn'") }}, 0) as last_withdrawn_near,
    coalesce({{ yocto_to_near("r->>'last_unvested'") }}, 0) as last_unvested_near,
    cast(r->>'changed_ns' as double) as changed_ns,
    cast(r->>'finished_ns' as double) as finished_ns,
    coalesce({{ yocto_to_near("r->>'terminating_unvested'") }}, 0) as terminating_unvested_near,
    cast(r->>'gone_ns' as double) as gone_ns,
    cast(r->>'last_read_height' as bigint) as last_read_height,
    {{ is_latest("cast(r->>'lockup_no' as integer)") }} as is_latest
from rows
