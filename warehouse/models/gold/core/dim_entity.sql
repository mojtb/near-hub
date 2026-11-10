-- The reviewed wallet registry, plus what the chain says about each account today.
with accounts as (
    select * from {{ ref('stg_rpc__accounts') }} where is_latest
),

tx_counts as (
    select * from {{ ref('stg_fastnear__tx_counts') }} where is_latest
)

select
    e.account_id,
    e.entity,
    e.category,
    e.role,
    e.tier,
    e.track_holdings = 1 as tracks_holdings,
    e.track_contract_stats = 1 as tracks_contract_stats,
    e.crawl_transfers = 1 as crawls_transfers,
    e.evidence_level,
    e.source_url,
    e.note,
    a.account_exists,
    a.has_contract,
    a.balance_near,
    a.storage_bytes,
    t.cumulative_txns,
    a.snapshot_date as checked_on
from {{ ref('entities') }} e
left join accounts a using (account_id)
left join tx_counts t using (account_id)
