-- Supply and issuance per UTC day.
-- NearBlocks' total_supply for day D is compared in dq_reconciliation with the on-chain supply at the
-- first block of D+1. minted_near adds burned gas back to the change in supply, which isolates issuance.
-- circulating_supply_near comes from fct_circulating_supply_daily, because NearBlocks' own figure stopped moving on 2025-08-27.
-- Burn is gas minus the share paid to contracts (the developer gas rebate). That share changed from 0.3 to 0 with
-- protocol version 87, first read on 2026-11-05, so each day uses the newest config read on or before it; days
-- before the first read (2026-10-28) use the first read's rate, the 30% in force since mainnet launch.
with nb as (
    select * from {{ ref('stg_nearblocks__charts_v1') }} where is_latest
),

config_history as (
    select snapshot_date, contract_gas_reward_rate from {{ ref('stg_rpc__protocol_config') }}
),

first_config as (
    select arg_min(contract_gas_reward_rate, snapshot_date) as contract_gas_reward_rate from config_history
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

rated as (
    select
        nb.*,
        coalesce(c.contract_gas_reward_rate, f.contract_gas_reward_rate) as contract_gas_reward_rate
    from nb
    cross join first_config f
    asof left join config_history c on nb.date_day >= c.snapshot_date
),

base as (
    select
        nb.date_day,
        nb.total_supply_near,
        cs.circulating_supply_near,
        nb.circulating_supply_near as circulating_supply_near_nearblocks,
        c.onchain_supply_end_of_day_near,
        c.protocol_version,
        nb.gas_fee_near,
        nb.total_supply_near - lag(nb.total_supply_near) over (order by nb.date_day) as supply_change_near,
        nb.contract_gas_reward_rate,
        nb.gas_fee_near * (1 - nb.contract_gas_reward_rate) as burn_near,
        coalesce(t.treasury_reward_near, 0) as treasury_reward_near
    from rated nb
    left join chain_next_day c using (date_day)
    left join {{ ref('fct_circulating_supply_daily') }} cs using (date_day)
    left join treasury_rewards t using (date_day)
)

select
    *,
    supply_change_near + burn_near as minted_near,
    (supply_change_near + burn_near) * 365 / nullif(total_supply_near, 0) as minted_annualized_rate
from base
