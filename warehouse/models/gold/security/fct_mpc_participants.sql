-- MPC operators per day, read directly from v1.signer: at the first block of the UTC day where the archival node has been
-- asked, and otherwise by that date's nightly snapshot (read_from says which). The contract's first version kept its
-- participants as a map from account to id, the later one as a list of (account, id, details); both are read.
with state as (
    select snapshot_date, read_from, result->'Running' as r
    from ({{ contract_view_reads() }})
    where contract = 'v1.signer' and method = 'state' and (result->'Running') is not null
),

listed as (
    select snapshot_date, read_from, {{ explode("r->'parameters'->'participants'->'participants'") }} as p
    from state
    where (r->'parameters') is not null
),

mapped as (
    select snapshot_date, read_from, ids, unnest(json_keys(ids)) as account
    from (select snapshot_date, read_from, r->'participants'->'account_to_participant_id' as ids from state where (r->'parameters') is null)
    where ids is not null
)

select snapshot_date, p->>0 as operator_account_id, cast(p->>1 as integer) as participant_id, read_from
from listed
union all
select snapshot_date, account as operator_account_id, cast(json_extract_string(ids, '$."' || account || '"') as integer) as participant_id, read_from
from mapped
