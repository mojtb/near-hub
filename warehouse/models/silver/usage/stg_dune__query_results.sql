-- Rows of public Dune queries read through Dune's official API (ingest dataset dune/query_results), one bronze file per
-- page of up to 5,000 rows, keyed <query id>__p<page>. Builds empty until a DUNE_API_KEY with API access has run.
-- The hand readings of the dashboard page are in stg_dune_public__query_results.
{% set page_size = 5000 %}

with files as ({{ bronze_files('dune__query_results') }}),

pages as (
    select
        snapshot_date,
        cast(split_part(file_key, '__', 1) as bigint) as query_id,
        cast(regexp_extract(file_key, '__p([0-9]+)$', 1) as integer) as page,
        doc
    from files
),

rows as (
    select
        snapshot_date,
        query_id,
        page,
        cast(left(doc->>'execution_ended_at', 19) as timestamp) as generated_at,
        cast(doc->'result'->'metadata'->>'total_row_count' as bigint) as total_row_count,
        generate_subscripts(from_json(doc->'result'->'rows', '["JSON"]'), 1) as position,
        {{ explode("doc->'result'->'rows'") }} as row_doc
    from pages
)

select
    snapshot_date,
    query_id,
    generated_at,
    page * {{ page_size }} + position as row_index,
    count(*) over (partition by snapshot_date, query_id) >= max(total_row_count) over (partition by snapshot_date, query_id) as is_complete,
    row_doc
from rows
