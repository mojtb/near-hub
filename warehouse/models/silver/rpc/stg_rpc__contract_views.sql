-- file_key is <contract>__<method>. `result` stays as JSON; gold tables pick what they need.
with files as ({{ bronze_files('rpc__contract_views') }})

select
    snapshot_date,
    doc->>'contract' as contract,
    doc->>'method' as method,
    cast(doc->>'block_height' as bigint) as block_height,
    doc->'result' as result,
    {{ is_latest("doc->>'contract', doc->>'method'") }} as is_latest
from files
