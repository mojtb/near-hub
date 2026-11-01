-- Chain usage per UTC day. v1 and v3 are different NearBlocks products with different definitions,
-- so overlapping fields keep their suffix. See dq_reconciliation for how far they disagree.
with v1 as (select * from {{ ref('stg_nearblocks__charts_v1') }} where is_latest),
     txn as (select * from {{ ref('stg_nearblocks__txn_stats') }} where is_latest),
     adr as (select * from {{ ref('stg_nearblocks__address_stats') }} where is_latest),
     blk as (select * from {{ ref('stg_nearblocks__block_stats') }} where is_latest)

select
    d.date_day,
    coalesce(txn.txns, v1.txns) as txns,
    v1.txns as txns_v1,
    txn.txns as txns_v3,
    txn.meta_txns,
    txn.meta_txns * 1.0 / nullif(txn.txns, 0) as meta_txn_share,
    txn.receipts,
    coalesce(blk.blocks, v1.blocks) as blocks,
    blk.chunks,
    blk.shards,
    blk.gas_price_yocto,
    v1.active_accounts as active_accounts_v1,
    adr.active_accounts as active_accounts_v3,
    v1.active_contracts as active_contracts_v1,
    adr.active_contracts as active_contracts_v3,
    v1.new_accounts,
    v1.deleted_accounts,
    coalesce(adr.new_contracts, v1.new_contracts) as new_contracts,
    v1.unique_contracts,
    adr.meta_accounts,
    adr.meta_relayers,
    v1.multichain_txns,
    v1.gas_used,
    v1.gas_fee_near,
    v1.txn_fee_near as txn_fee_near_v1,
    txn.txn_fee_near as txn_fee_near_v3,
    v1.txn_fee_usd,
    coalesce(txn.txn_volume_near, v1.txn_volume_near) as txn_volume_near,
    v1.txn_volume_usd
from {{ ref('dim_date') }} d
left join v1 using (date_day)
left join txn using (date_day)
left join adr using (date_day)
left join blk using (date_day)
where v1.date_day is not null or txn.date_day is not null or adr.date_day is not null
