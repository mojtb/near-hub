-- Where a date has both the replay at its first block and the nightly read some hours later, a liquid staking token's
-- price must be the same or a little higher at night: it rises with each epoch's rewards, about 0.007% an epoch, and
-- never falls. More than 0.05% apart, or lower at night, means one of the two reads is of the wrong day or contract.
with replay as (
    select date_day, contract, {{ yocto_to_near("result->>'$'") }} as price_near
    from {{ ref('stg_rpc__contract_views_history') }}
    where is_latest and error is null and method = 'ft_price'
),

nightly as (
    select snapshot_date as date_day, contract, {{ yocto_to_near("result->>'$'") }} as price_near
    from {{ ref('stg_rpc__contract_views') }}
    where method = 'ft_price'
)

select r.date_day, r.contract, r.price_near as replayed, n.price_near as nightly, n.price_near / r.price_near - 1 as change
from replay r
join nightly n using (date_day, contract)
where n.price_near / r.price_near - 1 not between -0.000001 and 0.0005
