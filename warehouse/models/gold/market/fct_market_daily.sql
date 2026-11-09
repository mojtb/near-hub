-- depends_on: {{ ref('stg_nearblocks__charts_v1') }}, {{ ref('stg_nearblocks__price_stats') }}
-- NEAR price and market cap per UTC day, one column per measure. price_usd is the close of the UTC day from the first
-- source that has one: CoinMetrics, the longest independent reference rate, then Coinbase, DefiLlama and NearBlocks.
-- price_basis names the source. dq_reconciliation compares the four. NearBlocks stamps a day's price at 00:00 UTC, so the
-- value stamped D+1 is the close of D; it is read from /v3/price-stats, and from /v1/charts for days before that window.
-- market_cap_usd is price times the circulating supply this warehouse builds from the chain, in fct_circulating_supply_daily.
-- fully_diluted_value_usd is price times total supply, from fct_supply_daily.
with coinmetrics as (
    select date_day, price_usd, spot_volume_usd
    from {{ ref('stg_coinmetrics__asset_metrics') }}
    where is_latest and coinmetrics_asset = 'near'
),

coinbase as (select date_day, close_usd from {{ ref('stg_coinbase__candles') }} where is_latest),

defillama as (
    select date_day, price_usd from {{ ref('stg_defillama__peer_price') }}
    where is_latest and coin_id = 'near'
),

nearblocks as ({{ nearblocks_daily_close() }}),

priced as (
    select
        d.date_day,
        coalesce(cm.price_usd, cb.close_usd, dl.price_usd, nb.price_usd) as price_usd,
        case
            when cm.price_usd is not null then 'coinmetrics'
            when cb.close_usd is not null then 'coinbase'
            when dl.price_usd is not null then 'defillama'
            when nb.price_usd is not null then 'nearblocks'
        end as price_basis,
        cm.spot_volume_usd as reported_spot_volume_usd
    from {{ ref('dim_date') }} d
    left join coinmetrics cm using (date_day)
    left join coinbase cb using (date_day)
    left join defillama dl using (date_day)
    left join nearblocks nb using (date_day)
    where cm.date_day is not null or cb.date_day is not null or dl.date_day is not null or nb.date_day is not null
)

select
    p.date_day,
    p.price_usd,
    p.price_basis,
    p.price_usd * cs.circulating_supply_near as market_cap_usd,
    p.price_usd * s.total_supply_near as fully_diluted_value_usd,
    p.reported_spot_volume_usd
from priced p
left join {{ ref('fct_circulating_supply_daily') }} cs using (date_day)
left join {{ ref('fct_supply_daily') }} s using (date_day)
