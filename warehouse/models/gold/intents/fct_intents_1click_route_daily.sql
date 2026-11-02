-- Finished 1Click swaps per UTC day, by how funds came in and went out, from the Intents Explorer API.
select date_day, deposit_type, recipient_type, swaps, amount_in_usd
from {{ ref('stg_intents_explorer__routes') }}
where is_latest
