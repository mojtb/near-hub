-- ETH and SOL are priced in two gold tables: here, and in fct_peer_daily as Ethereum's and Solana's price. Both read
-- CoinMetrics' PriceUSD for the same asset, fetched under two datasets, so the two may differ only by what CoinMetrics
-- restated between the reads. On 2026-11-13 they were identical on 738 and 720 of 741 days and the largest gap was
-- 0.012% (SOL, 2026-05-31). A gap over 0.1% on any day means the two tables no longer hold one figure.
select t.date_day, t.symbol, t.price_usd, p.price_usd as peer_price_usd
from {{ ref('fct_token_price_daily') }} t
join {{ ref('peers') }} pe on pe.coinmetrics_asset = t.source_asset_id
join {{ ref('fct_peer_daily') }} p on p.chain_id = pe.chain_id and p.date_day = t.date_day
where t.price_source = 'coinmetrics'
    and p.price_basis = 'coinmetrics'
    and abs(t.price_usd - p.price_usd) > 0.001 * p.price_usd
