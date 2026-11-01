with files as ({{ bronze_files('nearblocks__intents_volume_by_chain') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        r->>'blockchain' as blockchain,
        cast(r->>'volume' as double) as volume_usd,
        cast(r->>'swaps' as bigint) as swaps
    from rows
)

select *, {{ is_latest('date_day, blockchain') }} as is_latest
from typed
where date_day < snapshot_date
