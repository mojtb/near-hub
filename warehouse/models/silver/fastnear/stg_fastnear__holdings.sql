-- Point in time: fungible tokens and native NEAR per tracked account, per snapshot.
with files as ({{ bronze_files('fastnear__account_full') }}),

tokens as (
    select snapshot_date, doc->>'account_id' as account_id, {{ explode("doc->'tokens'") }} as t from files
),

token_rows as (
    select
        snapshot_date,
        account_id,
        t->>'contract_id' as token_id,
        t->>'balance' as balance_raw,
        cast(t->>'last_update_block_height' as bigint) as last_update_height
    from tokens
),

native_rows as (
    select
        snapshot_date,
        doc->>'account_id' as account_id,
        'native:near' as token_id,
        doc->'state'->>'balance' as balance_raw,
        null::bigint as last_update_height
    from files
    where (doc->'state'->>'balance') is not null
)

select *, {{ is_latest('account_id, token_id') }} as is_latest
from (select * from token_rows union all select * from native_rows)
