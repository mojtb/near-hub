-- Every service in registry/swap_services.csv must have a series that reaches the newest days of the table. The fetch
-- refuses a reply that carries another id than the registry's, so a listing DefiLlama renamed or regrouped would
-- otherwise drop out of the comparison without a sound, and NEAR Intents would look larger beside what is left.
with newest as (select max(date_day) as newest_day from {{ ref('fct_swap_services_daily') }})

select s.service_id, max(f.date_day) as service_newest_day, newest.newest_day
from {{ ref('swap_services') }} s
cross join newest
left join {{ ref('fct_swap_services_daily') }} f using (service_id)
group by all
having max(f.date_day) is null or newest.newest_day - max(f.date_day) > 3
