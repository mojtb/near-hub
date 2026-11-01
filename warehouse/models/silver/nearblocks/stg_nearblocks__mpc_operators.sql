-- MPC operators as NearBlocks reports them, including the TEE status it shows for each.
with files as ({{ bronze_files('nearblocks__mpc_operators') }}),

rows as (
    select
        snapshot_date,
        cast(doc->'data'->>'threshold' as integer) as threshold,
        {{ explode("doc->'data'->'participants'") }} as p
    from files
)

select
    snapshot_date,
    threshold,
    p->>'account' as operator_account_id,
    cast(p->>'is_validator' as boolean) as is_validator,
    p->'tee'->>'status' as tee_status,
    p->'tee'->>'expiry' as tee_expiry,
    p->'tee'->>'image_hash' as tee_image_hash,
    p->>'url' as node_url
from rows
