-- 1Click volume and app fees per UTC day, referral channel and status, tallied from the Intents Explorer API.
with files as ({{ bronze_files('intents_explorer__daily_tally') }}),

rows as (
    select snapshot_date, cast(doc->>'day' as date) as date_day, {{ explode("doc->'channels'") }} as c from files
)

select
    snapshot_date,
    date_day,
    coalesce(c->>'referral', '(none)') as referral,
    c->>'status' as status,
    cast(c->>'swaps' as bigint) as swaps,
    cast(c->>'amount_in_usd' as double) as amount_in_usd,
    cast(c->>'amount_out_usd' as double) as amount_out_usd,
    cast(c->>'app_fee_usd' as double) as app_fee_usd,
    snapshot_date = max(snapshot_date) over (partition by date_day) as is_latest
from rows
