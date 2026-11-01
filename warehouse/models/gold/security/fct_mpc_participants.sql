-- MPC operators per snapshot, read directly from v1.signer.
with state as (
    select snapshot_date, result->'Running'->'parameters'->'participants'->'participants' as participants
    from {{ ref('stg_rpc__contract_views') }}
    where contract = 'v1.signer' and method = 'state' and (result->'Running') is not null
),

rows as (
    select snapshot_date, {{ explode('participants') }} as p from state
)

select
    snapshot_date,
    p->>0 as operator_account_id,
    cast(p->>1 as integer) as participant_id
from rows
