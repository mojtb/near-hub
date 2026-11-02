-- 1Click volume and app fees per UTC day, referral channel and status, from the Intents Explorer API.
select date_day, referral, status, swaps, amount_in_usd, amount_out_usd, app_fee_usd
from {{ ref('stg_intents_explorer__channels') }}
where is_latest
