-- CoinMetrics' daily reference rate for each asset in registry/token_prices.csv that it prices, one file per asset.
-- PriceUSD is its fixed closing price at 00:00 UTC as the day ends, and CoinMetrics stamps the row with the day's own
-- date, so the row dated D is the close of D. The asset id is read from each row, as CoinMetrics wrote it.
with files as ({{ bronze_files('coinmetrics__token_price') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        r->>'asset' as coinmetrics_asset,
        cast(left(r->>'time', 10) as date) as date_day,
        cast(r->>'PriceUSD' as double) as price_usd
    from rows
)

select *, {{ is_latest('coinmetrics_asset, date_day', 'price_usd') }} as is_latest
from typed
where date_day < snapshot_date
