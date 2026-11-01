-- Coinbase returns [time, low, high, open, close, volume], newest first, with volume in NEAR.
with files as ({{ bronze_files('coinbase__candles') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as c from files
),

typed as (
    select
        snapshot_date,
        {{ unix_day("c->>0") }} as date_day,
        cast(c->>1 as double) as low_usd,
        cast(c->>2 as double) as high_usd,
        cast(c->>3 as double) as open_usd,
        cast(c->>4 as double) as close_usd,
        cast(c->>5 as double) as volume_near
    from rows
)

select *, {{ is_latest('date_day', 'close_usd') }} as is_latest
from typed
where date_day < snapshot_date
