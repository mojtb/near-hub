-- NEAR's own monthly revenue series, from revenue.near.org. The newest month may be incomplete. The page's running
-- totals are exactly the sums of these months, so they are not repeated here.
select month_start, revenue_usd, revenue_near
from {{ ref('stg_revenue_page__revenue_monthly') }}
where is_latest
