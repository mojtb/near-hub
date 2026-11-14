-- One row per page BigQuery returned: which query ran, with which parameters, what it read and what Google billed for it.
-- Each of the ten datasets saves the same head on every page, so this is where a result's cost and its exact SQL are found.
{% set datasets = ['tables', 'partitions', 'circulating_supply', 'blocks_daily', 'transactions_daily', 'actions_daily', 'signer_cohorts', 'signers_daily', 'callers_daily', 'staking_balances_daily'] %}

with files as (
    {% for name in datasets %}
    select '{{ name }}' as dataset, snapshot_date, file_key, doc from ({{ bronze_files('bigquery__' ~ name) }})
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    dataset,
    snapshot_date,
    regexp_replace(file_key, '__p[0-9]+$', '') as read_key,
    cast(doc->>'page' as integer) as page,
    doc->>'query' as query,
    cast(left(replace(doc->>'read_at', 'T', ' '), 19) as timestamp) as read_at,
    doc->>'sql_sha256' as sql_sha256,
    cast(doc->'parameters'->>'first_day' as date) as first_day,
    cast(doc->'parameters'->>'last_day' as date) as last_day,
    cast(doc->>'bytes_estimated' as bigint) as bytes_estimated,
    cast(doc->>'bytes_processed' as bigint) as bytes_processed,
    cast(doc->>'bytes_billed' as bigint) as bytes_billed,
    cast(doc->>'cache_hit' as boolean) as is_cache_hit,
    cast(doc->>'total_rows' as bigint) as total_rows,
    json_array_length(doc->'rows') as rows_on_page
from files
