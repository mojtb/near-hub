-- Finished 1Click swaps per UTC day, by how funds came in and went out, tallied from the Intents Explorer API.
with files as ({{ bronze_files('intents_explorer__daily_tally') }}),

rows as (
    select snapshot_date, cast(doc->>'day' as date) as date_day, {{ explode("doc->'routes'") }} as r from files
)

select
    snapshot_date,
    date_day,
    r->>'deposit_type' as deposit_type,
    r->>'recipient_type' as recipient_type,
    cast(r->>'swaps' as bigint) as swaps,
    cast(r->>'amount_in_usd' as double) as amount_in_usd,
    snapshot_date = max(snapshot_date) over (partition by date_day) as is_latest
from rows
