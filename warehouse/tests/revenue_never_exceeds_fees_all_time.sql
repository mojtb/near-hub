-- Sweeps can make one day's revenue exceed that day's fees, but never across all time.
select sum(revenue_usd_defillama) as revenue, sum(fees_usd_defillama) as fees
from {{ ref('fct_intents_daily') }}
having sum(revenue_usd_defillama) > sum(fees_usd_defillama)
