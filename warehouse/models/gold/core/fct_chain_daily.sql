-- Chain usage per UTC day, one column per measure. NearBlocks serves most counts twice: /v3 returns the last 365 days of
-- each read, which accumulate across snapshots, and /v1 returns every day since 2020-07-21 but is switched off on
-- 2026-11-22. Where both count the same thing they agree day for day, so the measure takes /v3 and falls back to /v1 for
-- older days, and dq_reconciliation holds the two to each other. Where they count different things both stay, under names
-- that say what each counts: active_signers (/v1) and active_accounts_with_relayed (/v3), new_contracts_v1 and _v3.
with v1 as (select * from {{ ref('stg_nearblocks__charts_v1') }} where is_latest),
     txn as (select * from {{ ref('stg_nearblocks__txn_stats') }} where is_latest),
     adr as (select * from {{ ref('stg_nearblocks__address_stats') }} where is_latest),
     blk as (select * from {{ ref('stg_nearblocks__block_stats') }} where is_latest)

select
    d.date_day,
    coalesce(txn.txns, v1.txns) as txns,
    txn.meta_txns,
    txn.meta_txns * 1.0 / nullif(txn.txns, 0) as meta_txn_share,
    txn.receipts,
    coalesce(blk.blocks, v1.blocks) as blocks,
    blk.chunks,
    blk.shards,
    blk.gas_price_yocto,
    v1.active_accounts as active_signers,
    adr.active_accounts as active_accounts_with_relayed,
    coalesce(adr.active_contracts, v1.active_contracts) as active_contracts,
    v1.new_accounts,
    v1.deleted_accounts,
    v1.new_contracts as new_contracts_v1,
    adr.new_contracts as new_contracts_v3,
    v1.unique_contracts,
    adr.meta_accounts,
    adr.meta_relayers,
    coalesce(blk.gas_used, v1.gas_used) as gas_used,
    coalesce(blk.gas_fee_near, v1.gas_fee_near) as gas_fee_near,
    coalesce(txn.txn_fee_near, v1.txn_fee_near) as txn_fee_near,
    coalesce(txn.txn_volume_near, v1.txn_volume_near) as txn_volume_near
from {{ ref('dim_date') }} d
left join v1 using (date_day)
left join txn using (date_day)
left join adr using (date_day)
left join blk using (date_day)
where v1.date_day is not null or txn.date_day is not null or adr.date_day is not null or blk.date_day is not null
