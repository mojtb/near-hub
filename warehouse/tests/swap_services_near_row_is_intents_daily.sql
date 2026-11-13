-- NEAR Intents' rows in fct_swap_services_daily repeat fct_intents_daily.volume_usd so that the comparison is one query.
-- The two must stay equal day for day, in both directions, or the table would hold a second figure for NEAR.
select coalesce(f.date_day, d.date_day) as date_day, f.volume_usd as in_swap_services, d.volume_usd as in_intents_daily
from (select date_day, volume_usd from {{ ref('fct_swap_services_daily') }} where is_near_intents) f
full join (select date_day, volume_usd from {{ ref('fct_intents_daily') }} where volume_usd is not null) d using (date_day)
where f.volume_usd is distinct from d.volume_usd
