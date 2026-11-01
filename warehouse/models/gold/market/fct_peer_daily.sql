-- NEAR and peer chains per day on the same definitions: DefiLlama for activity, CoinMetrics for price and
-- market cap, DefiLlama prices where CoinMetrics has no series. Empty cells mean the source has no value.
with peers as (select * from {{ ref('peers') }}),

tvl as (
    select p.chain_id, t.date_day, t.tvl_usd
    from {{ ref('stg_defillama__chain_tvl') }} t join peers p using (llama_chain) where t.is_latest
),

fees as (
    select p.chain_id, f.date_day,
        sum(f.value_usd) filter (where f.data_type = 'dailyFees') as fees_usd,
        sum(f.value_usd) filter (where f.data_type = 'dailyRevenue') as revenue_usd
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
    coalesce(cm.price_usd, llama_price.price_usd) as price_usd,
    cm.market_cap_usd,
    tvl.tvl_usd,
    fees.fees_usd,
    fees.revenue_usd,
    dex.volume_usd as dex_volume_usd,
    stable.stablecoins_usd
from keys k
left join tvl using (chain_id, date_day)
left join fees using (chain_id, date_day)
left join dex using (chain_id, date_day)
left join stable using (chain_id, date_day)
left join cm using (chain_id, date_day)
left join llama_price using (chain_id, date_day)
