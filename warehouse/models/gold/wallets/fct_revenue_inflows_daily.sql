-- NEAR's captured revenue rebuilt from wallet transfers, following DefiLlama's published method:
-- NEAR and wNEAR received by the three revenue wallets, excluding hops between those wallets.
-- This needs no Dune access and no NEAR-uploaded data, so it is an independent check on revenue.
select
    date_day,
    account_id,
    count(*) as transfers,
    sum(amount_token) as received_near,
    sum(amount_usd) as received_usd
from {{ ref('fct_wallet_transfers') }}
where account_id in ('fefundsadmin.sputnik-dao.near', '1csfundsadmin.sputnik-dao.near', 'buybacks.multisignature.near')
  and asset_id in ('native:near', 'nep141:wrap.near')
  and direction = 'in'
  and not is_between_revenue_wallets
  and counterparty_id <> 'system'
group by all
