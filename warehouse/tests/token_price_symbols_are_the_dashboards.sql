-- fct_token_price_daily exists to be joined to the pool's assets on symbol and day, so every symbol in
-- registry/token_prices.csv must be spelled as NEAR's dashboard series spells it. The spelling is case sensitive, and a price
-- under a spelling the dashboard does not use would join to nothing without a sound.
select t.symbol
from {{ ref('token_prices') }} t
where t.symbol not in (select symbol from {{ ref('fct_dune_intents_tvl_asset_daily') }})
