with files as ({{ bronze_files('nearblocks__address_stats') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'active_accounts' as bigint) as active_accounts,
        cast(r->>'active_contracts' as bigint) as active_contracts,
        cast(r->>'meta_accounts' as bigint) as meta_accounts,
        cast(r->>'meta_relayers' as bigint) as meta_relayers,
        cast(r->>'new_contracts' as bigint) as new_contracts
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
