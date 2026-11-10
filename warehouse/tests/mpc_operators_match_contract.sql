-- On each date with both readings, NearBlocks must list the same MPC operators as the contract. Both sides are the
-- nightly snapshot's reads, minutes apart. fct_mpc_participants is not used here: it prefers the read at the day's first
-- block, hours earlier, so on a day an operator joined or left it could differ without either being wrong.
with contract as (
    select snapshot_date, p->>0 as operator_account_id
    from (
        select snapshot_date, {{ explode("result->'Running'->'parameters'->'participants'->'participants'") }} as p
        from {{ ref('stg_rpc__contract_views') }}
        where contract = 'v1.signer' and method = 'state' and (result->'Running') is not null
    )
),
     indexer as (select snapshot_date, operator_account_id from {{ ref('fct_mpc_operators') }})
select * from (select * from contract except select * from indexer)
where snapshot_date in (select snapshot_date from indexer)
union all
select * from (select * from indexer except select * from contract)
where snapshot_date in (select snapshot_date from contract)
