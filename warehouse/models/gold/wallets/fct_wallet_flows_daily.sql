-- Transfers summed per wallet, day, asset and direction. Internal hops between revenue wallets are split out.
-- amount_usd sums only the transfers FastNear valued; amount_usd_estimated also prices NEAR and wNEAR at the day's close.
select
    date_day,
    account_id,
    asset_id,
    direction,
    is_between_revenue_wallets,
    count(*) as transfers,
    count(distinct counterparty_id) as counterparties,
    sum(amount_token) as amount_token,
    sum(amount_usd) as amount_usd,
    sum(amount_usd_estimated) as amount_usd_estimated
from {{ ref('fct_wallet_transfers') }}
group by all
