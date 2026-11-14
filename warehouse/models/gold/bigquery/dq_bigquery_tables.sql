-- Is NEAR's public BigQuery dataset still being loaded, and how large is it? One row per table on the newest read: rows,
-- size, last change, and the newest day that has rows. NEAR Lake, the feed the dataset's published loader reads, was
-- switched off on 2026-03-24 and the loader's repository has not changed since 2025, so this is checked, not assumed.
with tables as (select * from {{ ref('stg_bigquery__tables') }} where is_latest),

parts as (
    select
        table_name,
        min(date_day) as first_day_with_rows,
        max(date_day) as newest_day_with_rows,
        count(distinct date_day) as days_with_rows
    from {{ ref('stg_bigquery__partitions') }}
    where is_latest and date_day is not null and total_rows > 0
    group by table_name
)

select
    t.snapshot_date,
    t.table_name,
    t.table_type,
    t.row_count,
    t.size_bytes / 1e9 as size_gb,
    t.created_at,
    t.last_modified_at,
    p.first_day_with_rows,
    p.newest_day_with_rows,
    p.days_with_rows,
    date_diff('day', p.newest_day_with_rows, t.snapshot_date) as days_behind_read
from tables t
left join parts p using (table_name)
