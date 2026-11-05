-- Point in time: what Rhea lists as each token's USD price. The list is one JSON object with about 4,700 keys, so it is read
-- as a map: json_keys() would copy the whole document onto every row. Symbol is the contract's own claim, so never join on it.
-- price_first_read is the first read in the current run of one identical price, compared digit by digit as text. Most of the
-- list does not change between reads, even when NEAR moves, so the read date alone would make those prices look fresh.
with files as ({{ bronze_files('rhea__token_prices') }}),

entries as (
    select snapshot_date, unnest(map_entries(from_json(doc, '"MAP(VARCHAR, JSON)"'))) as e from files
),

prices as (
    select
        snapshot_date,
        e.key as token_id,
        nullif(e.value->>'symbol', '') as symbol,
        try_cast(e.value->>'decimal' as integer) as decimals,
        e.value->>'price' as price_text
    from entries
),

changes as (
    select
        *,
        price_text is distinct from lag(price_text) over (partition by token_id order by snapshot_date) as is_new_price
    from prices
),

runs as (
    select
        *,
        sum(cast(is_new_price as integer)) over (partition by token_id order by snapshot_date) as price_run
    from changes
)

select
    snapshot_date,
    token_id,
    symbol,
    decimals,
    try_cast(price_text as double) as price_usd,
    min(snapshot_date) over (partition by token_id, price_run) as price_first_read,
    {{ is_latest('token_id') }} as is_latest
from runs
