-- NAV and market price per trading day, from the charts on Bitwise's page for its NEAR ETF (NRR). Each snapshot repeats
-- recent days, so the newest snapshot of a day is the one to use.
with files as ({{ bronze_files('nrr_fund__figures') }}),

nav as (
    select snapshot_date, cast(r->>'day' as date) as date_day, cast(r->>'value' as double) as nav_usd
    from (select snapshot_date, {{ explode("doc->'nav_chart'") }} as r from files)
),

price as (
    select snapshot_date, cast(r->>'day' as date) as date_day, cast(r->>'value' as double) as market_price_usd
    from (select snapshot_date, {{ explode("doc->'market_price_chart'") }} as r from files)
)

select snapshot_date, date_day, nav_usd, market_price_usd, {{ is_latest('date_day') }} as is_latest
from nav
full join price using (snapshot_date, date_day)
