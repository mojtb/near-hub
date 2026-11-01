-- Validator sets from both datasets: nightly current set and past epochs read from the archival node.
with current_files as ({{ bronze_files('rpc__validators_current') }}),
epoch_files as ({{ bronze_files('rpc__validators_epoch') }}),

all_files as (
    select snapshot_date, 'nightly' as read_from, doc from current_files
    union all
    select snapshot_date, 'archival' as read_from, doc from epoch_files
),

rows as (
    select
        snapshot_date,
        read_from,
        cast(doc->>'epoch_height' as bigint) as epoch_height,
        cast(doc->>'epoch_start_height' as bigint) as epoch_start_height,
        {{ explode("doc->'validators'") }} as v
    from all_files
),

typed as (
    select
        snapshot_date,
        read_from,
        epoch_height,
        epoch_start_height,
        v->>'account_id' as validator_account_id,
        {{ yocto_to_near("v->>'stake'") }} as stake_near,
        cast(v->>'is_slashed' as boolean) as is_slashed,
        cast(v->>'num_produced_blocks' as bigint) as blocks_produced,
        cast(v->>'num_expected_blocks' as bigint) as blocks_expected,
        cast(v->>'num_produced_chunks' as bigint) as chunks_produced,
        cast(v->>'num_expected_chunks' as bigint) as chunks_expected,
        cast(v->>'num_produced_endorsements' as bigint) as endorsements_produced,
        cast(v->>'num_expected_endorsements' as bigint) as endorsements_expected
    from rows
)

-- An epoch read after it ended has final counts, so archival reads win over the nightly mid-epoch read.
select *,
    row_number() over (
        partition by epoch_height, validator_account_id
        order by case read_from when 'archival' then 0 else 1 end, snapshot_date desc
    ) = 1 as is_latest
from typed
