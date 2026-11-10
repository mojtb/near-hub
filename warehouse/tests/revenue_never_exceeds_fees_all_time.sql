-- Sweeps can make one day's revenue exceed that day's fees, but never across all time.
select sum(revenue_usd) as revenue, sum(fees_usd) as fees
from {{ ref('fct_intents_daily') }}
having sum(revenue_usd) > sum(fees_usd)
