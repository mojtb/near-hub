-- Validator set per epoch. The stakes and the set are fixed when an epoch starts, so they are right however the epoch was
-- read. The block, chunk and endorsement counts are final only for an epoch read after it ended: the nightly read catches
-- whichever epoch is running, and its counts stop where the read happened. Every block has one expected producer, so an
-- epoch is complete once its expected blocks add up to the protocol's epoch length. The backfill reads each nightly epoch
-- again after it ends, and silver then prefers that read.
with validators as (
    select * from {{ ref('stg_rpc__validators') }} where is_latest
),

epoch_length as (
    select arg_max(epoch_length_blocks, snapshot_date) as blocks from {{ ref('stg_rpc__protocol_config') }}
)

select
    v.epoch_height,
    v.epoch_start_height,
    v.validator_account_id,
    v.stake_near,
    v.stake_near / sum(v.stake_near) over (partition by v.epoch_height) as stake_share,
    row_number() over (partition by v.epoch_height order by v.stake_near desc, v.validator_account_id) as stake_rank,
    v.blocks_produced,
    v.blocks_expected,
    v.chunks_produced,
    v.chunks_expected,
    v.endorsements_produced,
    v.endorsements_expected,
    v.read_from,
    coalesce(sum(v.blocks_expected) over (partition by v.epoch_height) >= e.blocks, false) as is_epoch_complete
from validators v
cross join epoch_length e
