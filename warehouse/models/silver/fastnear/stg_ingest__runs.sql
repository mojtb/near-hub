-- One row per dataset per ingest run date, from the reports in data/bronze/_runs/.
with reports as (
    select
        cast(regexp_extract(filename, 'dt=(\d{4}-\d{2}-\d{2})', 1) as date) as snapshot_date,
        json as doc
    from read_json_objects('data/bronze/_runs/dt=*.json', filename = true, format = 'unstructured')
    where cast(regexp_extract(filename, 'dt=(\d{4}-\d{2}-\d{2})', 1) as date) <= cast('{{ var("as_of") }}' as date)
),

pairs as (
    select snapshot_date, doc, unnest(json_keys(doc)) as dataset from reports
)

select
    snapshot_date,
    dataset,
    doc->dataset->>'status' as status,
    doc->dataset->>'detail' as detail,
    cast(doc->dataset->>'files' as integer) as files,
    cast(doc->dataset->>'seconds' as double) as seconds
from pairs
