-- Who called the Chain Signatures contract and NEAR Intents' contract, from the dataset's receipt_actions table: one
-- row for each account among a contract's largest callers of the day by function calls, with the contract's totals for
-- the day repeated on every row. is_latest marks the rows of the newest read of each day.
with files as ({{ bronze_files('bigquery__callers_daily') }}),

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
        r->>'contract_id' as contract_id,
        r->>'caller_account_id' as caller_account_id,
        cast(r->>'calls' as bigint) as calls,
        cast(r->>'rank_by_calls' as integer) as rank_by_calls,
        cast(r->>'day_calls' as bigint) as day_calls,
        cast(r->>'day_callers' as bigint) as day_callers
    from rows
)

-- Two reads can sit in one snapshot, a first one and a wider one taken later. The later one wins.
select *, rank() over (partition by date_day order by snapshot_date desc, read_at desc nulls last, read_key desc) = 1 as is_latest
from typed
