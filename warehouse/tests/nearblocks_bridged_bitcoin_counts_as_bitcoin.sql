-- NearBlocks lists Bitcoin bridged to NEAR under near. Gold counts it as Bitcoin, as NEAR's own dashboard does. This
-- fails if a bridged Bitcoin token is on another chain in the asset table, or if moving it left the chain table with an
-- amount below zero.
select 'asset listed on ' || blockchain as problem, date_day, token_id as subject
from {{ ref('fct_intents_asset_daily') }}
where token_id in ({{ bridged_bitcoin_tokens() }}) and blockchain <> 'btc'

union all

select 'amount below zero', date_day, blockchain
from {{ ref('fct_intents_chain_daily') }}
where volume_usd < 0 or swaps < 0
