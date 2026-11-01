-- Every row of every widget read by hand from NEAR's public Intents dashboard on Dune. NEAR uploads the data
-- behind the dashboard. The file key holds the query id, the dashboard's filter values and a hash of the columns.
with files as ({{ bronze_files('dune_public__query_results') }}),

results as (
    select
        snapshot_date,
        file_key as reading_id,
        cast(split_part(file_key, '__', 1) as bigint) as query_id,
        regexp_replace(regexp_replace(file_key, '^[0-9]+(__)?', ''), '(__)?cols-[0-9a-f]+$', '') as selection,
        doc->'execution_succeeded' as result
    from files
)

select
    snapshot_date,
    reading_id,
    query_id,
    selection,
    cast(left(result->>'generated_at', 19) as timestamp) as generated_at,
    json_array_length(result->'data') >= cast(result->>'total_row_count' as bigint) as is_complete,
    generate_subscripts(from_json(result->'data', '["JSON"]'), 1) as row_index,
    {{ explode("result->'data'") }} as row_doc
from results
