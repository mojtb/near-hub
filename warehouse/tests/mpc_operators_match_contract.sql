-- On each date with both readings, NearBlocks must list the same MPC operators as the contract.
with contract as (select snapshot_date, operator_account_id from {{ ref('fct_mpc_participants') }}),
     indexer as (select snapshot_date, operator_account_id from {{ ref('fct_mpc_operators') }})
select * from (select * from contract except select * from indexer)
where snapshot_date in (select snapshot_date from indexer)
union all
select * from (select * from indexer except select * from contract)
where snapshot_date in (select snapshot_date from contract)
