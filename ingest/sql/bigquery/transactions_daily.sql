-- Transactions per UTC day, and each day's largest receivers, in one read of the transactions table.
-- A row with is_day_total = 1 is the whole day: transactions, the distinct accounts that signed one, and the distinct
-- accounts that received one. The other rows are single receivers: those among the day's top @top_n by transactions or
-- by distinct signers. Nothing below that rank leaves BigQuery, so no small account is copied out.
-- A signer here is the account that signed and paid for the transaction. When a relayer signs for a user, the relayer is
-- the signer and the user's own account is the receiver: actions_daily.sql counts those users at the contract they call.
-- Parameters: @first_day and @last_day, both inclusive, cut the read to those daily partitions; @top_n is the rank kept.
WITH grouped AS (
  SELECT
    block_date,
    receiver_account_id,
    GROUPING(receiver_account_id) AS is_day_total,
    COUNT(*) AS txns,
    COUNT(DISTINCT signer_account_id) AS signers,
    COUNT(DISTINCT receiver_account_id) AS receivers
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date BETWEEN @first_day AND @last_day
  GROUP BY GROUPING SETS ((block_date, receiver_account_id), (block_date))
),

ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY block_date, is_day_total ORDER BY txns DESC, receiver_account_id) AS rank_by_txns,
    ROW_NUMBER() OVER (PARTITION BY block_date, is_day_total ORDER BY signers DESC, receiver_account_id) AS rank_by_signers
  FROM grouped
)

SELECT
  block_date,
  is_day_total,
  IF(is_day_total = 1, NULL, receiver_account_id) AS receiver_account_id,
  txns,
  signers,
  receivers,
  IF(is_day_total = 1, NULL, rank_by_txns) AS rank_by_txns,
  IF(is_day_total = 1, NULL, rank_by_signers) AS rank_by_signers
FROM ranked
WHERE is_day_total = 1 OR rank_by_txns <= @top_n OR rank_by_signers <= @top_n
ORDER BY block_date, is_day_total DESC, rank_by_txns
