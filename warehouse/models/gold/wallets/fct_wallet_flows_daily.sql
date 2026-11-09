-- Transfers summed per wallet, day, asset and direction. Internal hops between revenue wallets are split out.
-- amount_usd sums each transfer's USD value: FastNear's where it gives one, else the day's close for NEAR and wNEAR.
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
