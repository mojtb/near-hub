-- The Bitwise NEAR ETF's (NRR) NEAR as seen on chain, per UTC day. It uses only the wallets Bitwise lists, read inside the
-- fund's staking pool. Shares are created and redeemed in baskets of 10,000, so NEAR that moves is rounded to whole
-- baskets. The chain settles about one trading day after the trade and nets orders against each other, so read
-- fct_etf_nrr_daily for what traded on a day, and this table for what reached the chain.
{% set reward_limit = 0.001 %}  {# Rewards add well under 0.1% to a wallet in a day. A larger change is NEAR moving in or out. #}

with rows as (select * from {{ ref('stg_rpc__nrr_pool_daily') }} where is_latest),

days as (
    select distinct date_day, block_height, delegators, other_delegators_near, snapshot_date from rows
),

grid as (
    select
        d.date_day,
        w.account_id,
        coalesce(r.staked_near + r.unstaked_near, 0) as near,
        coalesce(r.unstaked_near, 0) as unstaking_near
    from days d
    cross join (select distinct account_id from rows) w
    left join rows r on r.date_day = d.date_day and r.account_id = w.account_id
),

changes as (
    select
        *,
        coalesce(lag(near) over (partition by account_id order by date_day), 0) as near_before
    from grid
),

totals as (
    select
        date_day,
        count(*) filter (where near >= 1) as wallets_in_pool,
        sum(near) as near_in_wallets,
        sum(unstaking_near) as near_unstaking,
        coalesce(sum(near - near_before) filter (where near_before > 0 and abs(near - near_before) <= near_before * {{ reward_limit }}), 0) as rewards_near,
        coalesce(sum(near - near_before) filter (where not (near_before > 0 and abs(near - near_before) <= near_before * {{ reward_limit }})), 0) as moved_near
    from changes
    group by date_day
),

per_share as (
    select date_day, near_per_share from {{ ref('fct_etf_nrr_daily') }} where near_per_share is not null
),

settled as (
    select
        t.*,
        p.near_per_share,
        cast(round(t.moved_near / (p.near_per_share * 10000)) * 10000 as bigint) as settled_shares
    from totals t
    asof left join per_share p on t.date_day >= p.date_day
)

select
    s.date_day,
    d.block_height,
    s.wallets_in_pool,
    s.near_in_wallets,
    s.near_unstaking,
    s.rewards_near,
    s.moved_near,
    s.settled_shares,
    s.moved_near - s.settled_shares * s.near_per_share as left_over_near,
    sum(s.settled_shares) over (order by s.date_day) as running_settled_shares,
    s.moved_near * m.price_usd as moved_value_usd,
    s.near_in_wallets + d.other_delegators_near as pool_near,
    s.near_in_wallets / (s.near_in_wallets + d.other_delegators_near) as share_of_pool,
    s.near_in_wallets / m.circulating_supply_near as share_of_circulating_supply,
    d.snapshot_date
from settled s
join days d using (date_day)
left join {{ ref('fct_market_daily') }} m using (date_day)
