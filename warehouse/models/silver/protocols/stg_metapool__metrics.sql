-- Meta Pool's own metrics, parsed from its Prometheus text by ingest/parsers/prometheus.py.
with files as ({{ bronze_files('metapool__metrics_parsed') }}),

pairs as (
    select snapshot_date, doc, unnest(json_keys(doc)) as metric from files
)

select
    snapshot_date,
    metric,
    cast(doc->>metric as double) as value,
    {{ is_latest('metric') }} as is_latest
from pairs
