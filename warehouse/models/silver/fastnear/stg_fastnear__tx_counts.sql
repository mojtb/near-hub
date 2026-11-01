with files as ({{ bronze_files('fastnear__tx_counts') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as a from files
)

select
    snapshot_date,
    a->>'account_id' as account_id,
    cast(a->>'txs_count' as bigint) as cumulative_txns,
    {{ is_latest("a->>'account_id'") }} as is_latest
from rows
