-- App fees on finished 1Click swaps per UTC day and recipient, from the Intents Explorer API.
select date_day, recipient, entries, fee_usd
from {{ ref('stg_intents_explorer__fee_recipients') }}
where is_latest
