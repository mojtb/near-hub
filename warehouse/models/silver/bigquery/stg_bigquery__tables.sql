-- Every table and view in NEAR's public BigQuery dataset on the day it was read: rows, size and last change.
with files as ({{ bronze_files('bigquery__tables') }}),

rows as (
    select snapshot_date, {{ explode("doc->'rows'") }} as r from files
)

select
    snapshot_date,
    r->>'table_name' as table_name,
    r->>'table_type' as table_type,
    cast(left(replace(r->>'created_utc', 'T', ' '), 19) as timestamp) as created_at,
    cast(left(replace(r->>'last_modified_utc', 'T', ' '), 19) as timestamp) as last_modified_at,
    cast(r->>'row_count' as bigint) as row_count,
    cast(r->>'size_bytes' as bigint) as size_bytes,
    snapshot_date = max(snapshot_date) over () as is_latest
from rows
