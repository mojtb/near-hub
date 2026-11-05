-- What a sample of lockup contracts answered at past blocks, to hold the schedule formula to. By lockup number only.
with files as ({{ bronze_files('rpc__lockups') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as r from files where file_key = 'contract_views'
)

select
    snapshot_date,
    cast(r->>'read_day' as date) as read_day,
    cast(r->>'height' as bigint) as block_height,
    cast(r->>'block_ns' as double) as block_ns,
    cast(r->>'lockup_no' as integer) as lockup_no,
    {{ yocto_to_near("r->>'locked_yocto'") }} as contract_locked_near,
    cast(r->>'transfers_enabled' as boolean) as transfers_enabled
from rows
