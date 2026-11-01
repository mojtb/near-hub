-- Chain Signatures contract state per snapshot, read directly from v1.signer.
with state as (
    select snapshot_date, result from {{ ref('stg_rpc__contract_views') }}
    where contract = 'v1.signer' and method = 'state'
),

running as (
    select snapshot_date, result->'Running' as r from state where (result->'Running') is not null
)

select
    snapshot_date,
    json_array_length(r->'parameters'->'participants'->'participants') as participants,
    cast(r->'parameters'->>'threshold' as integer) as threshold,
    json_array_length(r->'domains'->'domains') as signature_domains,
    cast(r->'keyset'->>'epoch_id' as bigint) as keyset_epoch
from running
