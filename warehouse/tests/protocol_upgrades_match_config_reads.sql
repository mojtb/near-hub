-- registry/protocol_upgrades.csv dates a change in the contracts' share of gas to the block, and fct_supply_daily
-- trusts that date over the nightly config reads. So every read must agree with it: a read before the change's day
-- shows the old rate and a read after it the new one. A read on the day itself can show either, depending on the hour.
with upgrades as (
    select
        cast(first_block_utc as date) as change_day,
        contract_gas_reward_rate_before,
        contract_gas_reward_rate_after,
        lag(cast(first_block_utc as date)) over (order by first_block_utc) as previous_change_day,
        lead(cast(first_block_utc as date)) over (order by first_block_utc) as next_change_day
    from {{ ref('protocol_upgrades') }}
    where contract_gas_reward_rate_after is not null
)

select r.snapshot_date, r.contract_gas_reward_rate, u.change_day, u.contract_gas_reward_rate_before, u.contract_gas_reward_rate_after
from {{ ref('stg_rpc__protocol_config') }} r
cross join upgrades u
where (r.snapshot_date < u.change_day and r.snapshot_date > coalesce(u.previous_change_day, date '1970-01-01')
       and abs(r.contract_gas_reward_rate - u.contract_gas_reward_rate_before) > 1e-9)
   or (r.snapshot_date > u.change_day and r.snapshot_date < coalesce(u.next_change_day, date '9999-12-31')
       and abs(r.contract_gas_reward_rate - u.contract_gas_reward_rate_after) > 1e-9)
