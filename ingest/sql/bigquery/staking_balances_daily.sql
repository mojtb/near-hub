-- Who holds the staked NEAR, by day, in one read of the dataset's ft_balances_daily table. Despite its name the
-- table holds NEAR and not tokens: for each account that delegates stake, its liquid, staked and unstaked balance
-- and its reward at the day's last epoch, and the same again for its lockup account where it has one.
-- One row per day: how many accounts are listed and how many hold stake, the sums of each balance, and the stake held
-- by the 10, 100 and 1,000 accounts with the most, so a share of all listed stake can be worked out. An account's
-- stake here is its own and its lockup account's together. No account id leaves BigQuery.
-- Balances are FLOAT in the table and are returned as it holds them.
-- Parameters: @first_day and @last_day, both inclusive, cut the read to those daily partitions.
WITH newest AS (
  SELECT *
  FROM `bigquery-public-data.crypto_near_mainnet_us.ft_balances_daily`
  WHERE epoch_date BETWEEN @first_day AND @last_day
  QUALIFY ROW_NUMBER() OVER (PARTITION BY epoch_date, account_id ORDER BY SAFE_CAST(epoch_block_height AS INT64) DESC) = 1
),

ranked AS (
  SELECT
    *,
    IFNULL(staked, 0) + IFNULL(lockup_staked, 0) AS stake,
    ROW_NUMBER() OVER (PARTITION BY epoch_date ORDER BY IFNULL(staked, 0) + IFNULL(lockup_staked, 0) DESC, account_id) AS rank_by_stake
  FROM newest
)

SELECT
  epoch_date,
  COUNT(*) AS accounts,
  COUNTIF(stake > 0) AS accounts_with_stake,
  COUNTIF(lockup_account_id IS NOT NULL) AS accounts_with_lockup,
  MAX(SAFE_CAST(epoch_block_height AS INT64)) AS epoch_block_height,
  SUM(liquid) AS liquid,
  SUM(staked) AS staked,
  SUM(unstaked_not_liquid) AS unstaked_not_liquid,
  SUM(reward) AS reward,
  SUM(lockup_liquid) AS lockup_liquid,
  SUM(lockup_staked) AS lockup_staked,
  SUM(lockup_unstaked_not_liquid) AS lockup_unstaked_not_liquid,
  SUM(lockup_reward) AS lockup_reward,
  SUM(IF(rank_by_stake <= 10, stake, 0)) AS stake_top_10,
  SUM(IF(rank_by_stake <= 100, stake, 0)) AS stake_top_100,
  SUM(IF(rank_by_stake <= 1000, stake, 0)) AS stake_top_1000,
  MAX(stake) AS largest_stake
FROM ranked
GROUP BY epoch_date
ORDER BY epoch_date
