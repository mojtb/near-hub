-- From 2021 on, no single day should move total supply by more than 0.5%. Anything larger means bad data.
select date_day, total_supply_near, supply_change_near
from {{ ref('fct_supply_daily') }}
where date_day >= date '2021-01-01'
  and abs(supply_change_near) > 0.005 * total_supply_near
