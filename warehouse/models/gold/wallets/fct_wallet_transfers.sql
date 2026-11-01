-- Every transfer touching a crawled wallet. Amounts are signed from the wallet's point of view: out is negative.
with revenue_wallets as (
    select account_id from {{ ref('entities') }}
    where account_id in ('fefundsadmin.sputnik-dao.near', '1csfundsadmin.sputnik-dao.near', 'buybacks.multisignature.near')
)

select
    t.date_day,
    t.block_height,
    t.block_timestamp_ns,
    t.account_id,
    w.entity as account_entity,
    case when t.amount_token < 0 then 'out' else 'in' end as direction,
    t.counterparty_id,
    c.entity as counterparty_entity,
    c.category as counterparty_category,
    t.account_id in (select account_id from revenue_wallets)
        and t.counterparty_id in (select account_id from revenue_wallets) as is_between_revenue_wallets,
    t.asset_id,
    t.asset_type,
    t.transfer_type,
    t.method_name,
    t.amount_raw,
    t.amount_token,
    t.amount_usd,
    t.transaction_id,
    t.receipt_id,
    t.action_index,
    t.log_index,
    t.transfer_index,
    t.signer_id,
    t.predecessor_id
from {{ ref('stg_fastnear__transfers') }} t
left join {{ ref('entities') }} w on w.account_id = t.account_id
left join {{ ref('entities') }} c on c.account_id = t.counterparty_id
