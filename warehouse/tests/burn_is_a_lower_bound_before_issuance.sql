-- fct_supply_daily.burn_near assumes the contracts' share came out of all gas, so it calls itself a lower bound. Before
-- issuance began nothing was minted, so every fall in total supply was gas burned and the claim can be checked against the
-- chain: on each day before the first day supply rose (2020-10-20), supply must have fallen by at least burn_near.
-- Over those 79 days it fell by 84.8% of gas fees, against the 70% the column assumes.
with first_issuance as (
    select min(date_day) as date_day from {{ ref('fct_supply_daily') }} where supply_change_near > 0
)

select s.date_day, s.supply_change_near, s.burn_near
from {{ ref('fct_supply_daily') }} s
cross join first_issuance f
where s.date_day < f.date_day
  and s.burn_near > -s.supply_change_near * 1.001 + 1e-6
