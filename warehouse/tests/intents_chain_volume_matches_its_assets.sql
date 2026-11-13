-- NearBlocks serves public Intents volume by blockchain and by asset from one count: on every day a chain's volume and
-- swaps are the sums of its assets'. Moving bridged Bitcoin from near to btc relies on that, so this fails if the two
-- ever part.
with assets as (
    select date_day, blockchain, sum(volume_usd) as usd, sum(swaps) as swaps
    from {{ ref('fct_intents_asset_daily') }}
    group by date_day, blockchain
)

select c.date_day, c.blockchain, c.volume_usd as chain_usd, a.usd as assets_usd, c.swaps as chain_swaps, a.swaps as assets_swaps
from {{ ref('fct_intents_chain_daily') }} c
join assets a using (date_day, blockchain)
where abs(c.volume_usd - a.usd) > 1e-6 * greatest(c.volume_usd, a.usd, 1) or c.swaps <> a.swaps
