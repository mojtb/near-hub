-- Rows per daily partition of every table in the dataset, from BigQuery's own partition records. The tables are
-- partitioned by block_date, so date_day is the block's UTC day and total_rows is that day's count for the table.
-- BigQuery's own buckets ('__NULL__', '__UNPARTITIONED__') have no day and keep a null date_day.
-- The snapshot's own day, and any later day a late read found, are left out: they were not over when the snapshot was dated.
with files as ({{ bronze_files('bigquery__partitions') }}),

rows as (
    select snapshot_date, {{ explode("doc->'rows'") }} as r from files
)

select
    snapshot_date,
    r->>'table_name' as table_name,
    r->>'partition_id' as partition_id,
    cast(try_strptime(r->>'partition_id', '%Y%m%d') as date) as date_day,
    cast(r->>'total_rows' as bigint) as total_rows,
    cast(r->>'total_logical_bytes' as bigint) as total_logical_bytes,
    cast(left(replace(r->>'last_modified_utc', 'T', ' '), 19) as timestamp) as last_modified_at,
    snapshot_date = max(snapshot_date) over () as is_latest
from rows
where try_strptime(r->>'partition_id', '%Y%m%d') is null or cast(try_strptime(r->>'partition_id', '%Y%m%d') as date) < snapshot_date
