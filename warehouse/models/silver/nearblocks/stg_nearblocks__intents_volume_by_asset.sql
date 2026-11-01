with files as ({{ bronze_files('nearblocks__intents_volume_by_asset') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        r->>'blockchain' as blockchain,
        r->>'symbol' as symbol,
        r->>'token_id' as token_id,
        cast(r->>'volume' as double) as volume_token,
        cast(r->>'volume_usd' as double) as volume_usd,
        cast(r->>'swaps' as bigint) as swaps
    from rows
)

select *, {{ is_latest('date_day, token_id') }} as is_latest
from typed
where date_day < snapshot_date
