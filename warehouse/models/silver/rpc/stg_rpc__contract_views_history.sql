-- Contract views replayed at the first block of each UTC day, from the archival node: one file per day, one row per view.
-- `error` is the chain's own reason a view has no result: UNKNOWN_ACCOUNT or NO_CONTRACT_CODE where the contract did not
-- exist yet, CONTRACT_EXECUTION_ERROR where the call ran and failed. A day is read once; if it is ever read again, the
-- newest read is the one to use.
with files as ({{ bronze_files('rpc__contract_views_history') }}),

views as (
    select
        snapshot_date,
        cast(doc->>'day' as date) as date_day,
        cast(doc->>'block_height' as bigint) as block_height,
        {{ explode("doc->'views'") }} as v
    from files
)

select
    snapshot_date,
    date_day,
    block_height,
    v->>'contract' as contract,
    v->>'method' as method,
    v->'result' as result,
    v->>'error' as error,
    {{ is_latest("date_day, v->>'contract', v->>'method'") }} as is_latest
from views
