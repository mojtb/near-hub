-- NearBlocks' supply for day D must match the chain's first block of D+1 on every day both exist.
select date_day, total_supply_near, onchain_supply_end_of_day_near
from {{ ref('fct_supply_daily') }}
where abs(total_supply_near - onchain_supply_end_of_day_near) > 0.0001 * total_supply_near
