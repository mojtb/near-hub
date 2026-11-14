-- Every query this warehouse has run in BigQuery: which SQL file, over which days, how much data it read and what
-- Google billed. The SQL is in ingest/sql/bigquery/<query>.sql, and sql_sha256 is the hash of the text that ran, so a
-- result can be tied to the exact query. Google bills by gigabytes read; the first 1,000 GB of a month are free.
select
    snapshot_date,
    dataset,
    query,
    read_key,
    sql_sha256,
    max(read_at) as read_at,
    min(first_day) as first_day,
    max(last_day) as last_day,
    max(bytes_estimated) / 1e9 as gb_estimated,
    max(bytes_billed) / 1e9 as gb_billed,
    bool_or(is_cache_hit) as is_cache_hit,
    max(total_rows) as rows_returned,
    sum(rows_on_page) as rows_saved,
    count(*) as pages
from {{ ref('stg_bigquery__reads') }}
group by snapshot_date, dataset, query, read_key, sql_sha256
