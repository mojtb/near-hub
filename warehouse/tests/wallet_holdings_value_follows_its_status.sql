-- A row has a value exactly when its status says valued, the value is amount times price, and every other status holds what it claims.
select snapshot_date, account_id, token_id, decimals, amount_token, price_usd, price_source, price_date, value_usd, value_status
from {{ ref('fct_wallet_holdings') }}
where (value_usd is not null) <> (value_status = 'valued')
    or abs(value_usd - amount_token * price_usd) > 1e-9 * value_usd
    or (value_status = 'no_price' and price_usd is not null)
    or (value_status = 'no_decimals' and (decimals is not null or price_usd is null))
    or (value_status <> 'no_price' and (price_usd is null or price_source is null or price_date is null))
