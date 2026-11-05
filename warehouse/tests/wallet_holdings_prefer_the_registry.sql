-- registry/tokens.csv wins over what a contract says about itself, and a row has an amount exactly when its decimals are known.
select h.snapshot_date, h.account_id, h.token_id, h.symbol, h.decimals, h.metadata_source, h.amount_token
from {{ ref('fct_wallet_holdings') }} h
left join {{ ref('tokens') }} t on t.token_id = h.token_id
where (t.token_id is not null and (h.symbol <> t.symbol or h.decimals <> t.decimals or h.metadata_source <> 'registry'))
    or (h.decimals is null) <> (h.amount_token is null)
