-- Transfers summed per wallet, day, asset and direction. Internal hops between revenue wallets are split out.
select
    date_day,
    account_id,
    asset_id,
    direction,
    is_between_revenue_wallets,
    count(*) as transfers,
    count(distinct counterparty_id) as counterparties,
    sum(amount_token) as amount_token,
    sum(amount_usd) as amount_usd
from {{ ref('fct_wallet_transfers') }}
group by all
