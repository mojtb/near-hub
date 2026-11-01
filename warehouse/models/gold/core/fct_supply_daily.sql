-- Supply and issuance per UTC day.
-- NearBlocks' total_supply for day D is compared in dq_reconciliation with the on-chain supply at the
-- first block of D+1. minted_near adds burned gas back to the change in supply, which isolates issuance.
with nb as (
    select * from {{ ref('stg_nearblocks__charts_v1') }} where is_latest
),

config as (
    select contract_gas_reward_rate from {{ ref('stg_rpc__protocol_config') }} where is_latest
),

chain_next_day as (
    select date_day - 1 as date_day, total_supply_near as onchain_supply_end_of_day_near, protocol_version
    from {{ ref('dim_block_day') }}
),

treasury_rewards as (
    select date_day, sum(amount_token) as treasury_reward_near
    from {{ ref('stg_fastnear__transfers') }}
    where account_id = 'treasury.near' and transfer_type = 'EpochRewards'
    group by date_day
),

base as (
    select
        nb.date_day,
        nb.total_supply_near,
        nb.circulating_supply_near,
        c.onchain_supply_end_of_day_near,
        c.protocol_version,
        nb.gas_fee_near,
        nb.total_supply_near - lag(nb.total_supply_near) over (order by nb.date_day) as supply_change_near,
        nb.gas_fee_near * (1 - config.contract_gas_reward_rate) as burn_near,
        coalesce(t.treasury_reward_near, 0) as treasury_reward_near
    from nb
    cross join config
    left join chain_next_day c using (date_day)
    left join treasury_rewards t using (date_day)
)

select
    *,
    supply_change_near + burn_near as minted_near,
    (supply_change_near + burn_near) * 365 / nullif(total_supply_near, 0) as minted_annualized_rate
from base
