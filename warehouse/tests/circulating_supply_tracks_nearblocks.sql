-- While NearBlocks computed circulating supply from the same contracts, with its own code and its own list of lockups, the two must
-- stay close. The window left out is NearBlocks' own failure: from 2024-08-12 its job counted a lockup it could not read as nothing
-- locked, which pushed its figure towards total supply, and from 2024-11-04 such a failure stopped the job, until 2024-12-28.
select c.date_day, c.circulating_supply_near, n.circulating_supply_near as circulating_supply_near_nearblocks
from {{ ref('fct_circulating_supply_daily') }} c
join {{ ref('stg_nearblocks__charts_v1') }} n on n.date_day = c.date_day and n.is_latest
where c.date_day between date '2020-10-13' and date '2025-08-26'
  and c.date_day not between date '2024-08-12' and date '2024-12-28'
  and abs(c.circulating_supply_near - n.circulating_supply_near) > 0.005 * c.circulating_supply_near
