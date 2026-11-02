-- App fees on finished 1Click swaps per UTC day and recipient, tallied from the Intents Explorer API. A recipient is
-- named only if registry/entities.csv lists it; every other recipient is summed into (other).
with files as ({{ bronze_files('intents_explorer__daily_tally') }}),

rows as (
    select snapshot_date, cast(doc->>'day' as date) as date_day, {{ explode("doc->'fee_recipients'") }} as r from files
)

select
    snapshot_date,
    date_day,
    r->>'recipient' as recipient,
    cast(r->>'entries' as bigint) as entries,
    cast(r->>'fee_usd' as double) as fee_usd,
    snapshot_date = max(snapshot_date) over (partition by date_day) as is_latest
from rows
