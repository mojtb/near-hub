-- 1Click marks a token it has replaced by adding (DEPRECATED) to its symbol. Symbols group volume by asset, so the
-- mark must be gone by the time a symbol reaches a gold table, however 1Click spells it.
select 'fct_intents_1click_pair_daily, origin' as place, origin_symbol as symbol
from {{ ref('fct_intents_1click_pair_daily') }}
where origin_symbol ilike '%deprecated%'
union all
select 'fct_intents_1click_pair_daily, destination', destination_symbol
from {{ ref('fct_intents_1click_pair_daily') }}
where destination_symbol ilike '%deprecated%'
union all
select 'fct_wallet_holdings', symbol
from {{ ref('fct_wallet_holdings') }}
where symbol ilike '%deprecated%'
