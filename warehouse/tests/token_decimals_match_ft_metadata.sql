-- Registry decimals were read by hand from each contract's ft_metadata. The fetcher reads the same view, and both must agree.
select t.token_id, t.decimals as registry_decimals, m.decimals as contract_decimals
from {{ ref('tokens') }} t
join {{ ref('stg_rpc__ft_metadata') }} m on m.token_id = t.token_id and m.is_latest
where t.decimals <> m.decimals
