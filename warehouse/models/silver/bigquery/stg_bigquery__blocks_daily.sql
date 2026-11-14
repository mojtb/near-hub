-- Blocks per UTC day from the dataset's blocks table. A day is read again by every later run that reaches it; is_latest
-- marks the rows of the newest read of each day, so a day first read while it was still loading is replaced whole.
with files as ({{ bronze_files('bigquery__blocks_daily') }}),

rows as (
    select snapshot_date, regexp_replace(file_key, '__p[0-9]+$', '') as read_key, doc->>'read_at' as read_at,
        {{ explode("doc->'rows'") }} as r
    from files
),

typed as (
    select
        snapshot_date,
        read_key,
        read_at,
        cast(r->>'block_date' as date) as date_day,
        cast(r->>'blocks' as bigint) as blocks,
        cast(r->>'first_block_height' as bigint) as first_block_height,
        cast(r->>'last_block_height' as bigint) as last_block_height,
        cast(left(replace(r->>'first_block_utc', 'T', ' '), 19) as timestamp) as first_block_at,
        cast(left(replace(r->>'last_block_utc', 'T', ' '), 19) as timestamp) as last_block_at,
        -- The dataset stores total supply as a floating-point number of yoctoNEAR, so it is exact to about 15 digits.
        cast(r->>'total_supply_yocto' as double) / 1e24 as total_supply_near,
        cast(r->>'block_producers' as bigint) as block_producers
    from rows
)

-- Two reads can sit in one snapshot, a first one and a wider one taken later. The later one wins.
select *, rank() over (partition by date_day order by snapshot_date desc, read_at desc nulls last, read_key desc) = 1 as is_latest
from typed
