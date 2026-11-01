-- Daily transactions and unique callers per registry contract, from NearBlocks.
select
    c.date_day,
    c.account_id,
    e.entity,
    e.category,
    c.txns,
    c.unique_callers,
    c.unique_receivers
from {{ ref('stg_nearblocks__contract_txns') }} c
left join {{ ref('entities') }} e using (account_id)
where c.is_latest
