-- Point in time: tokens 1Click supports, with decimals and a live price. near_token_id is the NEAR contract an asset id
-- names, which is the token_id holdings use. It covers bridged assets too: USDC on Ethereum is listed with blockchain eth
-- and a 0x contract_address, but its asset id names eth-0xa0b8...eb48.omft.near, the contract intents.near holds.
-- 1Click marks a token it has replaced by adding (DEPRECATED) to its symbol, as in USDT(DEPRECATED). The symbol here
-- is without that mark, so volume in a replaced token still groups with the token that took its place;
-- listed_symbol keeps 1Click's own spelling.
with files as ({{ bronze_files('oneclick__tokens') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as t from files
)

select
    snapshot_date,
    t->>'assetId' as asset_id,
    t->>'blockchain' as blockchain,
    regexp_replace(t->>'symbol', '_?\(deprecated\)$', '', 'i') as symbol,
    t->>'symbol' as listed_symbol,
    coalesce(regexp_matches(t->>'symbol', '\(deprecated\)$', 'i'), false) as is_deprecated,
    cast(t->>'decimals' as integer) as decimals,
    cast(t->>'price' as double) as price_usd,
    try_cast(left(t->>'priceUpdatedAt', 10) as date) as price_date,
    t->>'contractAddress' as contract_address,
    nullif(regexp_extract(t->>'assetId', '^(?:1cs_v1:near:)?nep141:(.+)$', 1), '') as near_token_id,
    t->>'coingeckoId' as coingecko_id,
    {{ is_latest("t->>'assetId'") }} as is_latest
from rows
