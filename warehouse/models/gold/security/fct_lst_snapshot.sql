-- Liquid staking per snapshot, read directly from each contract. price_near is NEAR per token.
with views as (
    select snapshot_date, contract, method, result from {{ ref('stg_rpc__contract_views') }}
),

linear as (
    select
        snapshot_date,
        'LiNEAR' as token,
        'linear-protocol.near' as contract,
        max(case when method = 'ft_price' then {{ yocto_to_near("result->>'$'") }} end) as price_near,
        max(case when method = 'ft_total_supply' then {{ yocto_to_near("result->>'$'") }} end) as token_supply,
        max(case when method = 'get_total_staked_balance' then {{ yocto_to_near("result->>'$'") }} end) as staked_near
    from views
    where contract = 'linear-protocol.near'
    group by snapshot_date
),

rnear as (
    select
        snapshot_date,
        'rNEAR' as token,
        'lst.rhealab.near' as contract,
        max(case when method = 'ft_price' then {{ yocto_to_near("result->>'$'") }} end) as price_near,
        max(case when method = 'ft_total_supply' then {{ yocto_to_near("result->>'$'") }} end) as token_supply,
        null::decimal(38, 6) as staked_near
    from views
    where contract = 'lst.rhealab.near'
    group by snapshot_date
),

stnear as (
    select
        snapshot_date,
        'stNEAR' as token,
        'meta-pool.near' as contract,
        {{ yocto_to_near("result->>'st_near_price'") }} as price_near,
        {{ yocto_to_near("result->>'total_stake_shares'") }} as token_supply,
        {{ yocto_to_near("result->>'total_for_staking'") }} as staked_near
    from views
    where contract = 'meta-pool.near' and method = 'get_contract_state'
)

select * from linear
union all select * from rnear
union all select * from stnear
