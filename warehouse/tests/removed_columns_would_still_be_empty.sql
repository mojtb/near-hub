-- Gold leaves out a few fields the sources serve because they have never carried a value: a column that is the same on
-- every row tells a reader nothing and reads as if it did. Silver still holds them, and this test looks there. It fails
-- on the day one of them starts to say something, which is the day to put the column back into gold:
--   fct_validator_epoch.is_slashed     false for every validator in every epoch read (NEAR has not slashed anyone)
--   fct_mpc_operators.is_validator     false for every operator, and the three TEE fields none or empty (NearBlocks has no data)
--   fct_yield_pools base and reward    no NEAR pool has a reward APY, so base APY equals the total
--   dim_entity.locked_near             0 for every registry account, because none of them is a validator
select 'fct_validator_epoch.is_slashed' as column_to_restore, cast(count(*) as varchar) || ' validator rows are slashed' as what_changed
from {{ ref('stg_rpc__validators') }}
where is_slashed
having count(*) > 0

union all

select 'fct_mpc_operators: is_validator, tee_status, tee_expiry, tee_image_hash', cast(count(*) as varchar) || ' operator rows carry a value'
from {{ ref('stg_nearblocks__mpc_operators') }}
where is_validator
   or coalesce(nullif(lower(tee_status), ''), 'none') <> 'none'
   or tee_expiry is not null
   or tee_image_hash is not null
having count(*) > 0

union all

select 'fct_yield_pools: apy_base_pct, apy_reward_pct', cast(count(*) as varchar) || ' pool rows have a reward APY or a base APY that is not the total'
from {{ ref('stg_defillama__yield_pools') }}
where coalesce(apy_reward_pct, 0) <> 0
   or abs(coalesce(apy_base_pct, apy_pct) - apy_pct) > 1e-9
having count(*) > 0

union all

select 'dim_entity.locked_near', cast(count(*) as varchar) || ' registry account rows have NEAR locked for staking'
from {{ ref('stg_rpc__accounts') }}
where staked_near > 0
having count(*) > 0
