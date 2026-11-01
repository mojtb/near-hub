with files as ({{ bronze_files('nearblocks__contract_txns') }}),

rows as (
    select snapshot_date, file_key as account_id, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        account_id,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'txns' as bigint) as txns,
        cast(r->>'unique_address_in' as bigint) as unique_callers,
        cast(r->>'unique_address_out' as bigint) as unique_receivers
    from rows
)

select *, {{ is_latest('account_id, date_day') }} as is_latest
from typed
where date_day < snapshot_date
