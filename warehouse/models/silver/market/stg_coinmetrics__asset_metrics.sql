with files as ({{ bronze_files('coinmetrics__asset_metrics') }}),

rows as (
    select snapshot_date, file_key as coinmetrics_asset, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        coinmetrics_asset,
        cast(left(r->>'time', 10) as date) as date_day,
        cast(r->>'PriceUSD' as double) as price_usd,
        cast(r->>'CapMrktEstUSD' as double) as market_cap_usd,
        cast(r->>'volume_reported_spot_usd_1d' as double) as spot_volume_usd
    from rows
)

select *, {{ is_latest('coinmetrics_asset, date_day', 'price_usd') }} as is_latest
from typed
where date_day < snapshot_date
