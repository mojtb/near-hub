-- NEAR's own daily circulating and total supply, from the circulating_supply table of its public BigQuery dataset. The
-- table is read whole on every run, so each snapshot is a complete series and is_latest marks the newest read's rows.
-- The snapshot's own day, and any later day a late read found, are left out.
with files as ({{ bronze_files('bigquery__circulating_supply') }}),

rows as (
    select snapshot_date, {{ explode("doc->'rows'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(r->>'block_date' as date) as date_day,
        cast(r->>'computed_at_block_height' as bigint) as computed_at_block_height,
        cast(left(replace(r->>'computed_at_block_utc', 'T', ' '), 19) as timestamp) as computed_at,
        cast(r->>'circulating_tokens_supply' as double) / 1e24 as circulating_supply_near,
        cast(r->>'total_tokens_supply' as double) / 1e24 as total_supply_near
    from rows
)

select *, snapshot_date = max(snapshot_date) over () as is_latest
from typed
where date_day < snapshot_date
