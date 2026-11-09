-- NEAR's own year-to-date revenue versus emissions, from revenue.near.org. Kept separate from our
-- calculation in fct_supply_daily so the two can be compared. The page's percentages are these NEAR amounts over
-- reference_supply_near, so they are not repeated here.
select
    date_day,
    emissions_ytd_near,
    revenue_ytd_near,
    reference_supply_near
from {{ ref('stg_revenue_page__revenue_vs_emissions') }}
where is_latest
