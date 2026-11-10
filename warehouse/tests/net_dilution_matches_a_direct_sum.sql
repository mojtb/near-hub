-- fct_net_dilution_daily builds its 30-day sums with a window. This adds up the newest window's days straight from
-- the daily tables, so a window that slipped by a day or dropped the inflows would show.
with newest as (select * from {{ ref('fct_net_dilution_daily') }} order by date_day desc limit 1),

direct as (
    select sum(s.minted_near) as minted_near, sum(s.burn_near) as burn_near
    from {{ ref('fct_supply_daily') }} s, newest n
    where s.date_day > n.date_day - 30 and s.date_day <= n.date_day
),

inflows as (
    select coalesce(sum(r.received_near), 0) as inflow_near
    from {{ ref('fct_revenue_inflows_daily') }} r, newest n
    where r.date_day > n.date_day - 30 and r.date_day <= n.date_day
)

select n.date_day, n.minted_30d_near, d.minted_near, n.burn_30d_near, d.burn_near, n.revenue_inflow_30d_near, i.inflow_near
from newest n, direct d, inflows i
where abs(n.minted_30d_near - d.minted_near) > 1e-6 * d.minted_near
   or abs(n.burn_30d_near - d.burn_near) > 1e-6 * d.burn_near
   or abs(n.revenue_inflow_30d_near - i.inflow_near) > 1e-6 * greatest(i.inflow_near, 1)
