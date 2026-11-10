-- Supply and issuance per UTC day.
-- Total supply and gas fees come from NearBlocks /v3/block-stats, and from /v1/charts for days before /v3's window; the two
-- agree to the unit wherever both exist, and /v1 is switched off on 2026-11-22. dq_reconciliation compares the total with the
-- chain's own supply in the first block of the next day. minted_near adds burned gas back to the change in supply, which
-- isolates issuance. Circulating supply is in fct_circulating_supply_daily.
-- Burn is gas minus the share paid to contracts (the developer gas rebate). Each day uses the newest config read on
-- or before it, and days before the first read (2026-10-28) use the first read's rate, the 30% in force since mainnet
-- launch. A change that registry/protocol_upgrades.csv dates to the block holds from the next day even before a read
-- shows it, and its own day takes both rates weighted by the time each was in force, as if gas were spread evenly over
-- the day. The share went from 0.3 to 0 with protocol version 87 at 11:46:29 UTC on 2026-11-04, after that night's
-- config read, so that day reads 0.147.
with v1 as (select date_day, total_supply_near, gas_fee_near from {{ ref('stg_nearblocks__charts_v1') }} where is_latest),

v3 as (
    select date_day, total_supply_near, gas_fee_near
    from {{ ref('stg_nearblocks__block_stats') }}
    where is_latest and total_supply_near is not null
),

nb as (
    select
        date_day,
        coalesce(v3.total_supply_near, v1.total_supply_near) as total_supply_near,
        coalesce(v3.gas_fee_near, v1.gas_fee_near) as gas_fee_near
    from v1
    full join v3 using (date_day)
),

config_reads as (
    select snapshot_date, contract_gas_reward_rate from {{ ref('stg_rpc__protocol_config') }}
),

first_config as (
    select arg_min(contract_gas_reward_rate, snapshot_date) as contract_gas_reward_rate from config_reads
),

upgrades as (
    select
        cast(first_block_utc as date) as date_day,
        contract_gas_reward_rate_before,
        contract_gas_reward_rate_after,
        (epoch_ms(first_block_utc) - epoch_ms(cast(cast(first_block_utc as date) as timestamp))) / 86400000.0 as share_of_day_before
    from {{ ref('protocol_upgrades') }}
    where contract_gas_reward_rate_after is not null
),

config_history as (
    select snapshot_date as valid_from, contract_gas_reward_rate from config_reads
    union all
    select date_day + 1, contract_gas_reward_rate_after from upgrades
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
        coalesce(
            u.contract_gas_reward_rate_before * u.share_of_day_before + u.contract_gas_reward_rate_after * (1 - u.share_of_day_before),
            c.contract_gas_reward_rate,
            f.contract_gas_reward_rate
        ) as contract_gas_reward_rate
    from nb
    cross join first_config f
    asof left join config_history c on nb.date_day >= c.valid_from
    left join upgrades u on u.date_day = nb.date_day
),

base as (
    select
        nb.date_day,
        nb.total_supply_near,
        nb.total_supply_near - lag(nb.total_supply_near) over (order by nb.date_day) as supply_change_near,
        nb.contract_gas_reward_rate,
        nb.gas_fee_near * (1 - nb.contract_gas_reward_rate) as burn_near,
        coalesce(t.treasury_reward_near, 0) as treasury_reward_near
    from rated nb
    left join treasury_rewards t using (date_day)
)

select
    *,
    supply_change_near + burn_near as minted_near,
    (supply_change_near + burn_near) * 365 / nullif(total_supply_near, 0) as minted_annualized_rate
from base
