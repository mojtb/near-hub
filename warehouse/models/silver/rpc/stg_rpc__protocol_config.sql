-- Protocol parameters as read each night. Rates arrive as [numerator, denominator].
with files as ({{ bronze_files('rpc__protocol_config') }}),

config as (
    select snapshot_date, doc->'result' as c from files
)

select
    snapshot_date,
    cast(c->>'protocol_version' as integer) as protocol_version,
    cast(c->'max_inflation_rate'->>0 as double) / cast(c->'max_inflation_rate'->>1 as double) as max_inflation_rate,
    cast(c->'protocol_reward_rate'->>0 as double) / cast(c->'protocol_reward_rate'->>1 as double) as protocol_reward_rate,
    cast(c->'runtime_config'->'transaction_costs'->'burnt_gas_reward'->>0 as double)
        / cast(c->'runtime_config'->'transaction_costs'->'burnt_gas_reward'->>1 as double) as contract_gas_reward_rate,
    cast(c->>'epoch_length' as bigint) as epoch_length_blocks,
    cast(c->>'num_block_producer_seats' as integer) as block_producer_seats,
    cast(c->>'num_blocks_per_year' as bigint) as blocks_per_year_setting,
    cast(c->'runtime_config'->>'storage_amount_per_byte' as hugeint) as storage_yocto_per_byte,
    cast(c->>'min_gas_price' as hugeint) as min_gas_price_yocto,
    c->>'protocol_treasury_account' as protocol_treasury_account,
    json_array_length(c->'shard_layout'->'V3'->'shard_ids') as shard_count,
    {{ is_latest('1') }} as is_latest
from config
