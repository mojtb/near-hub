-- 1Click swaps per UTC day, tallied from the Intents Explorer API. No row or wallet address is stored. Empty until
-- INTENTS_EXPLORER_JWT is set. Recent days are tallied again each night, so the newest snapshot of a day is the one to use.
with files as ({{ bronze_files('intents_explorer__daily_tally') }})

select
    snapshot_date,
    cast(doc->>'day' as date) as date_day,
    cast(doc->>'pages' as bigint) as pages,
    cast(doc->>'swaps' as bigint) as swaps,
    cast(doc->>'senders' as bigint) as senders,
    cast(doc->>'recipients' as bigint) as recipients,
    snapshot_date = max(snapshot_date) over (partition by doc->>'day') as is_latest
from files
