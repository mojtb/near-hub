-- Point in time: tokens 1Click supports, with decimals and a live price.
with files as ({{ bronze_files('oneclick__tokens') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as t from files
)

select
    snapshot_date,
    t->>'assetId' as asset_id,
    t->>'blockchain' as blockchain,
    t->>'symbol' as symbol,
    cast(t->>'decimals' as integer) as decimals,
    cast(t->>'price' as double) as price_usd,
    t->>'contractAddress' as contract_address,
    t->>'coingeckoId' as coingecko_id,
    {{ is_latest("t->>'assetId'") }} as is_latest
from rows
