-- fct_wallet_holdings lets a price list's decimals stand in until a token's contract has been asked. That rests on the lists
-- being right, so wherever a contract has answered, the list that prices the token must agree with it. A row here means a
-- list counts whole tokens differently from the contract, and the holdings valued on that list need a look.
select p.token_id, p.price_source, p.price_decimals as list_decimals, m.decimals as contract_decimals
from {{ ref('fct_token_prices') }} p
join {{ ref('stg_rpc__ft_metadata') }} m on m.token_id = p.token_id and m.is_latest and m.decimals is not null
where p.price_decimals <> m.decimals
group by all
