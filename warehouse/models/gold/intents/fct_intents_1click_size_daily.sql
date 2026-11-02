-- Finished 1Click swaps per UTC day and size band, from the Intents Explorer API.
select date_day, size_band, swaps, amount_in_usd
from {{ ref('stg_intents_explorer__sizes') }}
where is_latest
