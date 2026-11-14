-- Signers by the month they first signed a transaction and each month they signed one again, counted over the whole
-- chain in BigQuery. The query reads all history each time, so every read is a complete table and is_latest marks the
-- newest. last_day is the last day that read covered: the month it falls in is not a whole month.
with files as ({{ bronze_files('bigquery__signer_cohorts') }}),

rows as (
    select
        snapshot_date,
        regexp_replace(file_key, '__p[0-9]+$', '') as read_key,
        doc->>'read_at' as read_at,
        cast(doc->'parameters'->>'last_day' as date) as last_day,
        {{ explode("doc->'rows'") }} as r
    from files
),

typed as (
    select
        snapshot_date,
        read_key,
        read_at,
        last_day,
        cast(r->>'cohort_month' as date) as cohort_month,
        cast(r->>'active_month' as date) as active_month,
        cast(r->>'signers' as bigint) as signers
    from rows
)

select *, rank() over (order by snapshot_date desc, read_at desc nulls last, read_key desc) = 1 as is_latest
from typed
