-- Legacy /v1/charts: the only full daily history back to 2020-07-21.
-- Its active_accounts differs from v3's address-stats, so it keeps a suffix in gold.
with files as ({{ bronze_files('nearblocks__charts_v1') }}),

rows as (
    select snapshot_date, {{ explode("doc->'charts'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'near_price' as double) as near_price_usd,
        cast(r->>'market_cap' as double) as market_cap_usd,
        {{ yocto_to_near("r->>'total_supply'") }} as total_supply_near,
        {{ yocto_to_near("r->>'circulating_supply'") }} as circulating_supply_near,
        cast(r->>'blocks' as bigint) as blocks,
        {{ yocto_to_near("r->>'gas_fee'") }} as gas_fee_near,
        cast(r->>'gas_used' as double) as gas_used,
        cast(r->>'txns' as bigint) as txns,
        {{ yocto_to_near("r->>'txn_volume'") }} as txn_volume_near,
        cast(r->>'txn_volume_usd' as double) as txn_volume_usd,
        {{ yocto_to_near("r->>'txn_fee'") }} as txn_fee_near,
        cast(r->>'txn_fee_usd' as double) as txn_fee_usd,
        cast(r->>'new_accounts' as bigint) as new_accounts,
        cast(r->>'active_accounts' as bigint) as active_accounts,
        cast(r->>'deleted_accounts' as bigint) as deleted_accounts,
        cast(r->>'new_contracts' as bigint) as new_contracts,
        cast(r->>'active_contracts' as bigint) as active_contracts,
        cast(r->>'unique_contracts' as bigint) as unique_contracts,
        cast(r->>'multichain_txns' as bigint) as multichain_txns
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
