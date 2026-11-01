-- House of Stake participation per snapshot, read directly from venear.dao.
with views as (
    select snapshot_date, method, result from {{ ref('stg_rpc__contract_views') }} where contract = 'venear.dao'
)

select
    snapshot_date,
    max(case when method = 'ft_total_supply' then {{ yocto_to_near("result->>'$'") }} end) as total_venear,
    max(case when method = 'get_num_accounts' then cast(result->>'$' as bigint) end) as accounts
from views
where method in ('ft_total_supply', 'get_num_accounts')
group by snapshot_date
