-- NEAR's own year-to-date revenue versus emissions, from revenue.near.org. Kept separate from our
-- calculation in fct_supply_daily so the two can be compared.
select
    date_day,
    emissions_ytd_near,
    revenue_ytd_near,
    reference_supply_near,
    gross_issuance_pct,
    net_issuance_pct,
    offset_pct
from {{ ref('stg_revenue_page__revenue_vs_emissions') }}
where is_latest
