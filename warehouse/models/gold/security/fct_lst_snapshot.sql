-- Liquid staking per day, read directly from each contract: at the first block of the UTC day where the archival node has
-- been asked, and otherwise by that date's nightly snapshot (read_from says which). price_near is NEAR per token, and
-- delegated_near is the NEAR the contract has staked with validators.
-- A contract's price is its staked NEAR divided by its token supply, so supply times price is the same figure: the two
-- agree within one part in a million for LiNEAR and stNEAR, and a test holds that. Where a read has no
-- get_total_staked_balance for rNEAR, its delegated NEAR is supply times price.
with views as (
    {{ contract_view_reads() }}
),

linear as (
    select
        snapshot_date,
        'LiNEAR' as token,
        'linear-protocol.near' as contract,
        max(case when method = 'ft_price' then {{ yocto_to_near("result->>'$'") }} end) as price_near,
        max(case when method = 'ft_total_supply' then {{ yocto_to_near("result->>'$'") }} end) as token_supply,
        max(case when method = 'get_total_staked_balance' then {{ yocto_to_near("result->>'$'") }} end) as delegated_near,
        read_from
    from views
    where contract = 'linear-protocol.near'
    group by snapshot_date, read_from
),

rnear as (
    select
        snapshot_date,
        'rNEAR' as token,
        'lst.rhealab.near' as contract,
        max(case when method = 'ft_price' then {{ yocto_to_near("result->>'$'") }} end) as price_near,
        max(case when method = 'ft_total_supply' then {{ yocto_to_near("result->>'$'") }} end) as token_supply,
        max(case when method = 'get_total_staked_balance' then {{ yocto_to_near("result->>'$'") }} end) as delegated_near,
        read_from
    from views
    where contract = 'lst.rhealab.near'
    group by snapshot_date, read_from
),

stnear as (
    select
        snapshot_date,
        'stNEAR' as token,
        'meta-pool.near' as contract,
        {{ yocto_to_near("result->>'st_near_price'") }} as price_near,
        {{ yocto_to_near("result->>'total_stake_shares'") }} as token_supply,
        {{ yocto_to_near("result->>'total_for_staking'") }} as delegated_near,
        read_from
    from views
    where contract = 'meta-pool.near' and method = 'get_contract_state'
)

select snapshot_date, token, contract, price_near, token_supply, coalesce(delegated_near, token_supply * price_near) as delegated_near, read_from
from (
    select * from linear
    union all select * from rnear
    union all select * from stnear
)
