-- A US-dollar price per UTC day for each main asset of the NEAR Intents pool, so that token balances read from the chain
-- can be valued without NEAR's own dashboard. The set and each asset's source are registry/token_prices.csv: every asset
-- that was at least 1% of the pool on the newest day of the dashboard's series when the set was chosen, other than wNEAR
-- (NEAR's price is fct_market_daily's) and the stablecoins (counted at one dollar). symbol is spelled as
-- fct_dune_intents_tvl_asset_daily spells it, so the two join on symbol and day.
-- One source per asset, never mixed within a series: CoinMetrics' reference rate where CoinMetrics has a series of the
-- asset's own, and DefiLlama's price otherwise. No price is worked out from the dashboard, from the 1Click token list or
-- from any figure NEAR publishes about the pool. The registry lists only assets that have a public price series.
-- Each series runs from the registry's first_price_day, the start of its unbroken daily run.
with tokens as (select * from {{ ref('token_prices') }} where price_source is not null),

coinmetrics as (
    select t.symbol, p.date_day, p.price_usd
    from {{ ref('stg_coinmetrics__token_price') }} p
    join tokens t on t.price_source = 'coinmetrics' and t.source_asset_id = p.coinmetrics_asset
    where p.is_latest
),

defillama as (
    select t.symbol, p.date_day, p.price_usd
    from {{ ref('stg_defillama__token_price') }} p
    join tokens t on t.price_source = 'defillama' and t.source_asset_id = p.coin_key
    where p.is_latest
),

prices as (
    select * from coinmetrics
    union all
    select * from defillama
)

select
    p.date_day,
    p.symbol,
    p.price_usd,
    t.price_source,
    t.source_asset_id,
    t.price_kind
from prices p
join tokens t using (symbol)
where p.price_usd is not null and p.date_day >= t.first_price_day
