-- Public Intents volume per asset per day, from NearBlocks. History starts when this dataset was first read.
select date_day, token_id, symbol, blockchain, volume_token, volume_usd, swaps
from {{ ref('stg_nearblocks__intents_volume_by_asset') }}
where is_latest
