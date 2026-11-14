-- Transactions per UTC day from the dataset's transactions table: one row for the whole day (is_day_total) and one for
-- each receiver among the day's largest by transactions or by distinct signers. is_latest marks the rows of the newest
-- read of each day: a later read replaces the day's whole list, so a receiver that fell out of it does not linger.
with files as ({{ bronze_files('bigquery__transactions_daily') }}),

rows as (
    select snapshot_date, regexp_replace(file_key, '__p[0-9]+$', '') as read_key, doc->>'read_at' as read_at,
        {{ explode("doc->'rows'") }} as r
    from files
),

typed as (
    select
        snapshot_date,
        read_key,
        read_at,
        cast(r->>'block_date' as date) as date_day,
        cast(r->>'is_day_total' as integer) = 1 as is_day_total,
        r->>'receiver_account_id' as receiver_account_id,
        cast(r->>'txns' as bigint) as txns,
        cast(r->>'signers' as bigint) as signers,
        cast(r->>'receivers' as bigint) as receivers,
        cast(r->>'rank_by_txns' as integer) as rank_by_txns,
        cast(r->>'rank_by_signers' as integer) as rank_by_signers
    from rows
)

-- Two reads can sit in one snapshot, a first one and a wider one taken later. The later one wins.
select *, rank() over (partition by date_day order by snapshot_date desc, read_at desc nulls last, read_key desc) = 1 as is_latest
from typed
