-- Staked NEAR per day in the dataset's table of staking balances (named ft_balances_daily): one row per day with the
-- accounts listed, the sums, and the stake of the 10, 100 and 1,000 largest holders. Amounts are in NEAR, as the
-- table holds them. is_latest marks the row of the newest read of each day.
with files as ({{ bronze_files('bigquery__staking_balances_daily') }}),

rows as (
    select snapshot_date, regexp_replace(file_key, '__p[0-9]+$', '') as read_key, doc->>'read_at' as read_at,
        {{ explode("doc->'rows'") }} as r
    from files
),

typed as (
    select
        snapshot_date,
        read_key,
        read_at,
        cast(r->>'epoch_date' as date) as date_day,
        cast(r->>'accounts' as bigint) as accounts,
        cast(r->>'accounts_with_stake' as bigint) as accounts_with_stake,
        cast(r->>'accounts_with_lockup' as bigint) as accounts_with_lockup,
        cast(r->>'epoch_block_height' as bigint) as epoch_block_height,
        cast(r->>'liquid' as double) as liquid_near,
        cast(r->>'staked' as double) as staked_near,
        cast(r->>'unstaked_not_liquid' as double) as unstaked_not_liquid_near,
        cast(r->>'reward' as double) as reward_near,
        cast(r->>'lockup_liquid' as double) as lockup_liquid_near,
        cast(r->>'lockup_staked' as double) as lockup_staked_near,
        cast(r->>'lockup_unstaked_not_liquid' as double) as lockup_unstaked_not_liquid_near,
        cast(r->>'lockup_reward' as double) as lockup_reward_near,
        cast(r->>'stake_top_10' as double) as stake_top_10_near,
        cast(r->>'stake_top_100' as double) as stake_top_100_near,
        cast(r->>'stake_top_1000' as double) as stake_top_1000_near,
        cast(r->>'largest_stake' as double) as largest_stake_near
    from rows
)

select *, rank() over (partition by date_day order by snapshot_date desc, read_at desc nulls last, read_key desc) = 1 as is_latest
from typed
