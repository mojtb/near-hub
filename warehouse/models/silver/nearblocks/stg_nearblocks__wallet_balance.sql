with files as ({{ bronze_files('nearblocks__wallet_balance') }}),

rows as (
    select snapshot_date, file_key as account_id, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        account_id,
        cast(left(r->>'date', 10) as date) as date_day,
        {{ yocto_to_near("r->>'amount'") }} as balance_near,
        {{ yocto_to_near("r->>'amount_staked'") }} as staked_near,
        cast(r->>'storage_usage' as bigint) as storage_bytes
    from rows
)

select *, {{ is_latest('account_id, date_day') }} as is_latest
from typed
where date_day < snapshot_date
