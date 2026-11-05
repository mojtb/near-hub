-- Registry decimals were read from each contract's ft_metadata. Where 1Click lists the token too, both must agree.
select t.token_id, t.decimals as registry_decimals, o.decimals as oneclick_decimals
from {{ ref('tokens') }} t
join (
    select contract_address, min(decimals) as decimals
    from {{ ref('stg_oneclick__tokens') }}
    where is_latest and blockchain = 'near' and contract_address is not null
    group by contract_address
) o on o.contract_address = t.token_id
where t.decimals <> o.decimals
