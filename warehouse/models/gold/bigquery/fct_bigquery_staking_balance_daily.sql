-- Staked NEAR by day and how much of it the largest holders have, from the table of staking balances in NEAR's public
-- BigQuery dataset. The dataset names that table ft_balances_daily, but it holds NEAR, not tokens: one row for each
-- account it follows, with the account's own stake and the stake of its lockup account.
-- Read it with care. The table follows more accounts each year (8,848 on its first day, 30,511 on 2026-11-13), so a
-- rise over time is partly the list growing: listed_share_of_stake says how much of all staked NEAR the day's list
-- holds, and only days near 1 can be read as the whole. Its liquid, unstaked and reward columns do not add up to
-- anything this warehouse can check (they sum to more than the supply), so they are left in bronze.
with rows as (select * from {{ ref('stg_bigquery__staking_balances_daily') }} where is_latest),

-- All staked NEAR on the day, from the validator set: the newest epoch read on or before it.
total as (
    select r.date_day, arg_max(v.total_stake_near, v.approx_date_day) as total_stake_near
    from rows r
    join {{ ref('fct_validator_summary') }} v on v.approx_date_day <= r.date_day and v.approx_date_day > r.date_day - 7
    group by 1
)

select
    r.date_day,
    r.accounts,
    r.accounts_with_stake,
    r.accounts_with_lockup,
    r.staked_near,
    r.lockup_staked_near,
    r.staked_near + r.lockup_staked_near as listed_stake_near,
    t.total_stake_near,
    (r.staked_near + r.lockup_staked_near) / nullif(t.total_stake_near, 0) as listed_share_of_stake,
    r.largest_stake_near,
    r.stake_top_10_near,
    r.stake_top_100_near,
    r.stake_top_1000_near,
    r.stake_top_10_near / nullif(r.staked_near + r.lockup_staked_near, 0) as top_10_share,
    r.stake_top_100_near / nullif(r.staked_near + r.lockup_staked_near, 0) as top_100_share,
    r.stake_top_1000_near / nullif(r.staked_near + r.lockup_staked_near, 0) as top_1000_share
from rows r
left join total t using (date_day)
