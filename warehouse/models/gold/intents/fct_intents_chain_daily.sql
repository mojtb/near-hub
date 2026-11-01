-- Public Intents volume per blockchain per day, from NearBlocks.
select date_day, blockchain, volume_usd, swaps
from {{ ref('stg_nearblocks__intents_volume_by_chain') }}
where is_latest
