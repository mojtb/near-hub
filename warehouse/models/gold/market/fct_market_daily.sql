-- NEAR price and market cap per day, all aligned to the close of the UTC day. price_usd prefers CoinMetrics,
-- the longest independent reference rate; each source keeps its own column for dq_reconciliation.
with coinmetrics as (
    select date_day, price_usd, market_cap_usd, spot_volume_usd
    from {{ ref('stg_coinmetrics__asset_metrics') }}
    where is_latest and coinmetrics_asset = 'near'
),

coinbase as (
    select date_day, open_usd, high_usd, low_usd, close_usd, volume_near from {{ ref('stg_coinbase__candles') }} where is_latest
),

defillama as (
    select date_day, price_usd from {{ ref('stg_defillama__peer_price') }}
    where is_latest and coin_id = 'near'
),

-- NearBlocks stamps price at the start of the day, so day D's close is the value stamped D+1.
nearblocks as (
    select
        date_day,
        lead(nullif(near_price_usd, 0)) over (order by date_day) as near_price_usd,
        lead(nullif(market_cap_usd, 0)) over (order by date_day) as market_cap_usd,
        circulating_supply_near
    from {{ ref('stg_nearblocks__charts_v1') }}
    where is_latest
)

select
    d.date_day,
    coalesce(cm.price_usd, dl.price_usd, nb.near_price_usd) as price_usd,
    coalesce(cm.market_cap_usd, nb.market_cap_usd) as market_cap_usd,
    cm.price_usd as price_usd_coinmetrics,
    cb.close_usd as price_usd_coinbase_close,
    dl.price_usd as price_usd_defillama,
    nb.near_price_usd as price_usd_nearblocks,
    cb.open_usd,
    cb.high_usd,
    cb.low_usd,
    cb.volume_near as coinbase_volume_near,
    cm.spot_volume_usd as reported_spot_volume_usd,
    nb.circulating_supply_near
from {{ ref('dim_date') }} d
left join coinmetrics cm using (date_day)
left join coinbase cb using (date_day)
left join defillama dl using (date_day)
left join nearblocks nb using (date_day)
where cm.date_day is not null or cb.date_day is not null or dl.date_day is not null or nb.date_day is not null
