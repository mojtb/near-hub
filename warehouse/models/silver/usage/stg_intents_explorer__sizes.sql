-- Finished 1Click swaps per UTC day and size band, tallied from the Intents Explorer API.
with files as ({{ bronze_files('intents_explorer__daily_tally') }}),

rows as (
    select snapshot_date, cast(doc->>'day' as date) as date_day, {{ explode("doc->'sizes'") }} as s from files
)

select
    snapshot_date,
    date_day,
    s->>'bucket' as size_band,
    cast(s->>'swaps' as bigint) as swaps,
    cast(s->>'amount_in_usd' as double) as amount_in_usd,
    snapshot_date = max(snapshot_date) over (partition by date_day) as is_latest
from rows
