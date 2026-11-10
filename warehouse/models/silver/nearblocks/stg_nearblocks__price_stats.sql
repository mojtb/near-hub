-- Daily NEAR price and market cap from NearBlocks /v3/price-stats. Like /v1/charts, which it replaces when /v1 is switched
-- off on 2026-11-22, it stamps a day's price at 00:00 UTC, so the value for day D is the close of day D-1; gold moves it back.
-- It equals /v1's price on every day both hold.
with files as ({{ bronze_files('nearblocks__price_stats') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'near_price' as double) as near_price_usd,
        cast(r->>'market_cap' as double) as market_cap_usd
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
