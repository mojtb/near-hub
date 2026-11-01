with files as ({{ bronze_files('nearblocks__txn_stats') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'txns' as bigint) as txns,
        cast(r->>'meta_txns' as bigint) as meta_txns,
        cast(r->>'receipts' as bigint) as receipts,
        cast(r->>'txn_fee' as double) as txn_fee_near,
        cast(r->>'txn_volume' as double) as txn_volume_near
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
