-- A row has a value exactly when its status says valued, the value is amount times the snapshot's price for that token in
-- fct_token_prices, and every other status holds what it claims.
select h.snapshot_date, h.account_id, h.token_id, h.decimals, h.amount_token, p.price_usd, p.price_source, p.price_date, h.value_usd, h.value_status
from {{ ref('fct_wallet_holdings') }} h
left join {{ ref('fct_token_prices') }} p on p.snapshot_date = h.snapshot_date and p.token_id = h.token_id
where (h.value_usd is not null) <> (h.value_status = 'valued')
    or abs(h.value_usd - h.amount_token * p.price_usd) > 1e-9 * h.value_usd
    or (h.value_status = 'no_price' and p.price_usd is not null)
    or (h.value_status = 'no_decimals' and (h.decimals is not null or p.price_usd is null))
    or (h.value_status <> 'no_price' and (p.price_usd is null or p.price_source is null or p.price_date is null))
