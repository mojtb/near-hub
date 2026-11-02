-- Finished 1Click swaps per UTC day and asset pair, tallied from the Intents Explorer API. Pairs under $1,000 on a
-- day are summed into one (other) row, so each day's total stays right.
with files as ({{ bronze_files('intents_explorer__daily_tally') }}),

rows as (
    select snapshot_date, cast(doc->>'day' as date) as date_day, {{ explode("doc->'pairs'") }} as p from files
)

select
    snapshot_date,
    date_day,
    p->>'origin_asset' as origin_asset,
    p->>'destination_asset' as destination_asset,
    cast(p->>'swaps' as bigint) as swaps,
    cast(p->>'amount_in_usd' as double) as amount_in_usd,
    cast(p->>'amount_out_usd' as double) as amount_out_usd,
    snapshot_date = max(snapshot_date) over (partition by date_day) as is_latest
from rows
