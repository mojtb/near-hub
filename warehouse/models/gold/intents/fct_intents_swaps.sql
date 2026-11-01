-- One row per 1Click swap from the Intents Explorer API. Empty until INTENTS_EXPLORER_JWT is set.
select
    date_day,
    created_at_unix,
    deposit_address,
    deposit_memo,
    origin_asset,
    destination_asset,
    status,
    referral,
    amount_in_usd,
    amount_out_usd
from {{ ref('stg_intents_explorer__swaps') }}
