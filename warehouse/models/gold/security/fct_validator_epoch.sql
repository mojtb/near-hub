-- Validator set per epoch. Epochs read after they ended carry final block and chunk counts.
with validators as (
    select * from {{ ref('stg_rpc__validators') }} where is_latest
)

select
    epoch_height,
    epoch_start_height,
    validator_account_id,
    stake_near,
    stake_near / sum(stake_near) over (partition by epoch_height) as stake_share,
    row_number() over (partition by epoch_height order by stake_near desc, validator_account_id) as stake_rank,
    is_slashed,
    blocks_produced,
    blocks_expected,
    chunks_produced,
    chunks_expected,
    endorsements_produced,
    endorsements_expected,
    read_from
from validators
