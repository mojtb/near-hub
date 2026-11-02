-- Finished 1Click swaps per UTC day and asset pair, from the Intents Explorer API. Symbols and chains come from the
-- 1Click token list, so an asset that has left the list has none.
with tokens as (
    select asset_id, symbol, blockchain from {{ ref('stg_oneclick__tokens') }} where is_latest
)

select
    p.date_day,
    p.origin_asset,
    o.symbol as origin_symbol,
    o.blockchain as origin_blockchain,
    p.destination_asset,
    d.symbol as destination_symbol,
    d.blockchain as destination_blockchain,
    p.swaps,
    p.amount_in_usd,
    p.amount_out_usd
from {{ ref('stg_intents_explorer__pairs') }} p
left join tokens o on o.asset_id = p.origin_asset
left join tokens d on d.asset_id = p.destination_asset
where p.is_latest
