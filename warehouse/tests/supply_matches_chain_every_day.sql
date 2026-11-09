-- NearBlocks' supply for day D must match the chain's first block of D+1 on every day both exist.
select s.date_day, s.total_supply_near, b.total_supply_near as onchain_supply_end_of_day_near
from {{ ref('fct_supply_daily') }} s
join {{ ref('dim_block_day') }} b on b.date_day = s.date_day + 1
where abs(s.total_supply_near - b.total_supply_near) > 0.0001 * s.total_supply_near
