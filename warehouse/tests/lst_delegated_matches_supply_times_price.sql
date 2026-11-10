-- A liquid-staking contract sets its price as the NEAR it has staked divided by its token supply, so supply times price
-- is its staked NEAR. fct_lst_snapshot leans on that to fill rNEAR's delegated_near before the contract's own figure was
-- read, so the identity must hold wherever the contract's figure is there: within 0.01%. Measured on LiNEAR and stNEAR
-- over nine nights, the two were under one part in a million apart.
select snapshot_date, token, delegated_near, token_supply * price_near as supply_times_price
from {{ ref('fct_lst_snapshot') }}
where abs(delegated_near / nullif(token_supply * price_near, 0) - 1) > 0.0001
