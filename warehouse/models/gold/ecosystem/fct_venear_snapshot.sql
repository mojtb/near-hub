-- House of Stake participation per day, read directly from venear.dao: at the first block of the UTC day where the
-- archival node has been asked, and otherwise by that date's nightly snapshot (read_from says which).
with views as (
    select snapshot_date, read_from, method, result from ({{ contract_view_reads() }}) where contract = 'venear.dao'
)

select
    snapshot_date,
    max(case when method = 'ft_total_supply' then {{ yocto_to_near("result->>'$'") }} end) as total_venear,
    max(case when method = 'get_num_accounts' then cast(result->>'$' as bigint) end) as accounts,
    read_from
from views
where method in ('ft_total_supply', 'get_num_accounts')
group by snapshot_date, read_from
