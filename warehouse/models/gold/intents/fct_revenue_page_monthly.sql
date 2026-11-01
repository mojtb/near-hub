-- NEAR's own monthly revenue series, from revenue.near.org. The newest month may be incomplete.
select month_start, revenue_usd, revenue_near, cumulative_revenue_usd, cumulative_revenue_near
from {{ ref('stg_revenue_page__revenue_monthly') }}
where is_latest
