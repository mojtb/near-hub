-- Every transfer touching a crawled wallet. Amounts are signed from the wallet's point of view: out is negative.
-- amount_usd is FastNear's value at transfer time where FastNear gives one, and otherwise, for NEAR and wNEAR, the amount
-- at the day's closing price from fct_market_daily, so a series can be summed in USD. usd_basis says which. The test
-- wallet_usd_estimate_tracks_fastnear holds the close-price figure to FastNear's where both exist.
with revenue_wallets as (
    select account_id from {{ ref('entities') }}
    where account_id in ('fefundsadmin.sputnik-dao.near', '1csfundsadmin.sputnik-dao.near', 'buybacks.multisignature.near')
),

near_assets as (
    select unnest(['native:near', 'nep141:wrap.near', 'nep245:intents.near:nep141:wrap.near']) as asset_id
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
    coalesce(t.amount_usd, case when n.asset_id is not null then t.amount_token * m.price_usd end) as amount_usd,
    case
        when t.amount_usd is not null then 'transfer_time'
        when n.asset_id is not null and m.price_usd is not null then 'daily_close'
    end as usd_basis,
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
left join near_assets n on n.asset_id = t.asset_id
left join {{ ref('fct_market_daily') }} m on m.date_day = t.date_day
