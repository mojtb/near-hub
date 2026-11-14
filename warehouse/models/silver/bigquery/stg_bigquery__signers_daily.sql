-- Who signed the day's transactions, from the dataset's transactions table: one row for each account among the day's
-- largest signers by transactions, or among the largest signers of the transactions sent to intents.near. The day's
-- totals are repeated on every row. is_latest marks the rows of the newest read of each day: a later read replaces the
-- day's whole list, so a signer that fell out of it does not linger.
with files as ({{ bronze_files('bigquery__signers_daily') }}),

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
        r->>'signer_account_id' as signer_account_id,
        cast(r->>'txns' as bigint) as txns,
        cast(r->>'receivers' as bigint) as receivers,
        cast(r->>'intents_txns' as bigint) as intents_txns,
        cast(r->>'rank_by_txns' as integer) as rank_by_txns,
        cast(r->>'rank_by_intents_txns' as integer) as rank_by_intents_txns,
        cast(r->>'day_txns' as bigint) as day_txns,
        cast(r->>'day_intents_txns' as bigint) as day_intents_txns,
        cast(r->>'day_intents_signers' as bigint) as day_intents_signers
    from rows
)

-- Two reads can sit in one snapshot, a first one and a wider one taken later. The later one wins.
select *, rank() over (partition by date_day order by snapshot_date desc, read_at desc nulls last, read_key desc) = 1 as is_latest
from typed
