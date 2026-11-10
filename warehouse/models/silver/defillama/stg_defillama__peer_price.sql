-- Daily price per peer from DefiLlama's price API. DefiLlama stamps each daily point near midnight UTC, but not exactly:
-- across the stored reads points sit up to about 2.4 hours either side, and roughly half land a few seconds after it.
-- A point near the midnight that starts day D+1 is the close of day D, so the timestamp is rounded to the nearest
-- midnight before the second is taken off. Taking the day of the raw timestamp instead dated half the points a day late,
-- made pairs of points share a date and left the next day empty (239 to 353 missing days per coin, found 2026-11-09).
-- file_key is <coin id>__<start date> or <coin id>__recent.
with files as ({{ bronze_files('defillama__peer_price') }}),

points as (
    select
        snapshot_date,
        split_part(file_key, '__', 1) as coin_id,
        {{ explode("doc->'coins'->('coingecko:' || split_part(file_key, '__', 1))->'prices'") }} as p
    from files
),

typed as (
    select
        snapshot_date,
        coin_id,
        {{ unix_day("cast(round(cast(p->>'timestamp' as bigint) / 86400.0) as bigint) * 86400 - 1") }} as date_day,
        cast(p->>'price' as double) as price_usd
    from points
)

select *, {{ is_latest('coin_id, date_day', 'price_usd') }} as is_latest
from typed
where date_day < snapshot_date
