-- NEAR and peer chains per day: DefiLlama for activity, CoinMetrics for price and market cap, DefiLlama prices where CoinMetrics
-- has no series (TON, and Sui before 2023-08-17); price_basis says which. NEAR's price and market cap are fct_market_daily's.
-- Empty cells mean the source has no value. Market caps are not on one definition. Each peer's uses the circulating
-- supply its project reports, collected by CoinGecko: on 2026-11-05 that was 41% of total supply for Sui and 100% for Ethereum.
-- NEAR's uses this warehouse's chain-built supply, which leaves out only lockups, so the Foundation's liquid NEAR counts as circulating.
with peers as (select * from {{ ref('peers') }}),

tvl as (
    select p.chain_id, t.date_day, t.tvl_usd
    from {{ ref('stg_defillama__chain_tvl') }} t join peers p using (llama_chain) where t.is_latest
),

fees as (
    select p.chain_id, f.date_day,
        sum(f.value_usd) filter (where f.data_type = 'dailyFees') as fees_usd,
        sum(f.value_usd) filter (where f.data_type = 'dailyRevenue') as revenue_usd,
        min(f.snapshot_date) as fee_read_date
    from {{ ref('stg_defillama__chain_fees') }} f join peers p using (llama_chain) where f.is_latest
    group by all
),

dex as (
    select p.chain_id, v.date_day, v.volume_usd
    from {{ ref('stg_defillama__chain_dex_volume') }} v join peers p using (llama_chain) where v.is_latest
),

stable as (
    select p.chain_id, s.date_day, s.stablecoins_usd
    from {{ ref('stg_defillama__stablecoin_chain') }} s join peers p using (llama_chain) where s.is_latest
),

cm as (
    select p.chain_id, m.date_day, m.price_usd, m.market_cap_usd
    from {{ ref('stg_coinmetrics__asset_metrics') }} m join peers p on p.coinmetrics_asset = m.coinmetrics_asset where m.is_latest
),

llama_price as (
    select p.chain_id, m.date_day, m.price_usd
    from {{ ref('stg_defillama__peer_price') }} m join peers p on p.coingecko_id = m.coin_id where m.is_latest
),

keys as (
    select chain_id, date_day from tvl
    union select chain_id, date_day from fees
    union select chain_id, date_day from dex
    union select chain_id, date_day from stable
    union select chain_id, date_day from cm
    union select chain_id, date_day from llama_price
)

select
    k.date_day,
    k.chain_id,
    case when k.chain_id = 'near' then near_cap.price_usd else coalesce(cm.price_usd, llama_price.price_usd) end as price_usd,
    case
        when k.chain_id = 'near' then near_cap.price_basis
        when cm.price_usd is not null then 'coinmetrics'
        when llama_price.price_usd is not null then 'defillama'
    end as price_basis,
    case when k.chain_id = 'near' then near_cap.market_cap_usd else cm.market_cap_usd end as market_cap_usd,
    case when k.chain_id = 'near' then near_cap.market_cap_usd / near_cap.price_usd else cm.market_cap_usd / cm.price_usd end as implied_supply_tokens,
    case
        when k.chain_id = 'near' and near_cap.market_cap_usd is not null then 'chain: total supply minus lockups'
        when k.chain_id <> 'near' and cm.market_cap_usd is not null then 'project-reported circulating supply, through CoinGecko and CoinMetrics'
    end as market_cap_basis,
    tvl.tvl_usd,
    fees.fees_usd,
    fees.revenue_usd,
    dex.volume_usd as dex_volume_usd,
    stable.stablecoins_usd,
    -- Measured on NEAR, whose fees are mostly Intents fees and settle with them. Every chain gets the same rule, so a
    -- filter on this column cuts all of them at the same day; only NEAR's figures are held to it by a test.
    coalesce(fees.fee_read_date - k.date_day < {{ var('intents_fee_settle_nights') }}, false) as is_fee_revenue_provisional
from keys k
left join tvl using (chain_id, date_day)
left join fees using (chain_id, date_day)
left join dex using (chain_id, date_day)
left join stable using (chain_id, date_day)
left join cm using (chain_id, date_day)
left join llama_price using (chain_id, date_day)
left join {{ ref('fct_market_daily') }} near_cap on k.chain_id = 'near' and near_cap.date_day = k.date_day
