-- Every row of every widget read in a browser, on request and never on a schedule, from NEAR's public Intents
-- dashboard on Dune. NEAR uploads the data behind the dashboard. The file key holds the query id, the dashboard's
-- filter values, a table page's row offset
-- after the first page, and a hash of the columns. A table read page by page has one file per page, so row_index
-- counts from the start of the result, and is_complete looks at all of a table's pages together. A response without
-- total_row_count was sent whole, within Dune's request_max_result_size_bytes, so its own rows are the total.
with files as ({{ bronze_files('dune_public__query_results') }}),

results as (
    select
        snapshot_date,
        file_key as reading_id,
        regexp_replace(file_key, '__offset-[0-9]+__', '__') as result_id,
        cast(split_part(file_key, '__', 1) as bigint) as query_id,
        regexp_replace(regexp_replace(regexp_replace(file_key, '^[0-9]+(__)?', ''), '(__)?cols-[0-9a-f]+$', ''), '(__)?offset-[0-9]+$', '') as selection,
        coalesce(cast(nullif(regexp_extract(file_key, '__offset-([0-9]+)__', 1), '') as bigint), 0) as row_offset,
        doc->'execution_succeeded' as result
    from files
),

rows as (
    select
        snapshot_date,
        reading_id,
        result_id,
        query_id,
        selection,
        row_offset,
        cast(left(result->>'generated_at', 19) as timestamp) as generated_at,
        coalesce(cast(result->>'total_row_count' as bigint), json_array_length(result->'data')) as total_row_count,
        generate_subscripts(from_json(result->'data', '["JSON"]'), 1) as position,
        {{ explode("result->'data'") }} as row_doc
    from results
)

select
    snapshot_date,
    reading_id,
    query_id,
    selection,
    generated_at,
    count(*) over (partition by snapshot_date, result_id) >= max(total_row_count) over (partition by snapshot_date, result_id) as is_complete,
    row_offset + position as row_index,
    row_doc
from rows
