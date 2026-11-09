-- Registry tokens with their decimals and CoinGecko id. Decimals come from the registry, where each was read from the
-- contract's ft_metadata; 1Click's figure is the fallback, and a data test holds the two to each other. Prices are in
-- fct_token_prices.
with oneclick as (
    select
        contract_address,
        min(decimals) as decimals,
        min(coingecko_id) as coingecko_id
    from {{ ref('stg_oneclick__tokens') }}
    where is_latest and blockchain = 'near' and contract_address is not null
    group by contract_address
)

select
    t.token_id,
    t.symbol,
    t.token_class,
    t.track_holders = 1 as tracks_holders,
    t.evidence_level,
    t.source_url,
    t.note,
    coalesce(t.decimals, o.decimals) as decimals,
    o.coingecko_id
from {{ ref('tokens') }} t
left join oneclick o on o.contract_address = t.token_id
