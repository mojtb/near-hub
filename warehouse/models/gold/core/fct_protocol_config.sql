-- Protocol parameters as read on each snapshot date. A change between rows is a protocol change.
select
    snapshot_date,
    protocol_version,
    max_inflation_rate,
    protocol_reward_rate,
    contract_gas_reward_rate,
    1 - contract_gas_reward_rate as gas_burn_rate,
    epoch_length_blocks,
    block_producer_seats,
    blocks_per_year_setting,
    shard_count,
    storage_yocto_per_byte,
    min_gas_price_yocto,
    protocol_treasury_account
from {{ ref('stg_rpc__protocol_config') }}
