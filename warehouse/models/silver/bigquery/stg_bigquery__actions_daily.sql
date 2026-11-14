-- Actions per UTC day from the dataset's receipt_actions table: one row per day and kind of action (is_kind_total), and
-- one for each contract among the day's largest by function calls, by distinct signers or by distinct callers.
-- is_latest marks the rows of the newest read of each day, so a later read replaces the day's whole list.
with files as ({{ bronze_files('bigquery__actions_daily') }}),

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
        r->>'action_kind' as action_kind,
        cast(r->>'is_kind_total' as integer) = 1 as is_kind_total,
        r->>'contract_id' as contract_id,
        cast(r->>'actions' as bigint) as actions,
        cast(r->>'signers' as bigint) as signers,
        cast(r->>'predecessors' as bigint) as predecessors,
        cast(r->>'receivers' as bigint) as receivers,
        cast(r->>'from_system' as bigint) as from_system,
        cast(r->>'rank_by_calls' as integer) as rank_by_calls,
        cast(r->>'rank_by_signers' as integer) as rank_by_signers,
        cast(r->>'rank_by_predecessors' as integer) as rank_by_predecessors
    from rows
)

-- Two reads can sit in one snapshot, a first one and a wider one taken later. The later one wins.
select *, rank() over (partition by date_day order by snapshot_date desc, read_at desc nulls last, read_key desc) = 1 as is_latest
from typed
