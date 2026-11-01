-- Daily price per peer from DefiLlama's price API. A point stamped 00:00 UTC on day D+1 is the close of day D.
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
        {{ unix_day("cast(p->>'timestamp' as bigint) - 1") }} as date_day,
        cast(p->>'price' as double) as price_usd
    from points
)

select *, {{ is_latest('coin_id, date_day', 'price_usd') }} as is_latest
from typed
where date_day < snapshot_date
