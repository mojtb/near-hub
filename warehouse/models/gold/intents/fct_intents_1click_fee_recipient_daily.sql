-- App fees on finished 1Click swaps per UTC day and recipient, from the Intents Explorer API.
select date_day, recipient, entries, fee_usd,
    coalesce(date_day >= {{ oneclick_daily_run_start() }}, false) as is_in_daily_run
from {{ ref('stg_intents_explorer__fee_recipients') }}
where is_latest
