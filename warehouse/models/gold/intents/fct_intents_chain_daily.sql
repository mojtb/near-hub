-- Public Intents volume per blockchain per day, from NearBlocks. NearBlocks lists a token under the chain its contract
-- is on, so Bitcoin bridged to NEAR (nbtc.bridge.near, which carries almost all Bitcoin swaps from 2026-05-06) arrives
-- under near. Here it is moved to btc, as NEAR's own dashboard counts it. NearBlocks' chain figures are exactly its
-- asset figures added up, so the move takes that token's amounts from stg_nearblocks__intents_volume_by_asset.
with chains as (
    select date_day, blockchain, volume_usd, swaps
    from {{ ref('stg_nearblocks__intents_volume_by_chain') }}
    where is_latest
),

bridged as (
    select date_day, listed_blockchain, blockchain, sum(volume_usd) as volume_usd, sum(swaps) as swaps
    from {{ ref('stg_nearblocks__intents_volume_by_asset') }}
    where is_latest and blockchain <> listed_blockchain
    group by date_day, listed_blockchain, blockchain
),

moved as (
    select date_day, blockchain, volume_usd, swaps from chains
    union all
    select date_day, listed_blockchain, -volume_usd, -swaps from bridged
    union all
    select date_day, blockchain, volume_usd, swaps from bridged
),

summed as (
    select date_day, blockchain, sum(volume_usd) as volume_usd, cast(sum(swaps) as bigint) as swaps
    from moved
    group by date_day, blockchain
)

select
    date_day,
    blockchain,
    -- Taking a token's amount from its chain's can leave a rounding remainder of a fraction of a cent.
    case when volume_usd between -0.01 and 0 then 0 else volume_usd end as volume_usd,
    swaps
from summed
