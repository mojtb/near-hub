-- DefiLlama's daily price for each asset in registry/token_prices.csv that it prices. coin_key is DefiLlama's own key
-- as the reply carries it, `coingecko:<id>` or `<chain>:<address>` for a token contract, so gold joins on it and not on
-- the file name, where a colon cannot stand. A window that came back empty, before a coin's first price, leaves no row.
-- A day is dated as in stg_defillama__peer_price: DefiLlama stamps each daily point near the midnight UTC that ends the
-- day, up to 2.4 hours either side, so the stamp is rounded to the nearest midnight before the second is taken off.
-- priced_at keeps the stamp itself.
with files as ({{ bronze_files('defillama__token_price') }}),

coins as (
    select snapshot_date, doc, unnest(json_keys(doc->'coins')) as coin_key from files
),

points as (
    select
        snapshot_date,
        coin_key,
        doc->'coins'->coin_key->>'symbol' as listed_symbol,
        cast(doc->'coins'->coin_key->>'confidence' as double) as confidence,
        {{ explode("doc->'coins'->coin_key->'prices'") }} as p
    from coins
),

typed as (
    select
        snapshot_date,
        coin_key,
        listed_symbol,
        confidence,
        {{ unix_day("cast(round(cast(p->>'timestamp' as bigint) / 86400.0) as bigint) * 86400 - 1") }} as date_day,
        make_timestamp(cast(p->>'timestamp' as bigint) * 1000000) as priced_at,
        cast(p->>'price' as double) as price_usd
    from points
)

select *, {{ is_latest('coin_key, date_day', 'price_usd') }} as is_latest
from typed
where date_day < snapshot_date
