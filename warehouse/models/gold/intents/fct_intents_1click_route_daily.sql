-- Finished 1Click swaps per UTC day, by how funds came in and went out, from the Intents Explorer API.
select date_day, deposit_type, recipient_type, swaps, amount_in_usd,
    coalesce(date_day >= {{ oneclick_daily_run_start() }}, false) as is_in_daily_run
from {{ ref('stg_intents_explorer__routes') }}
where is_latest
