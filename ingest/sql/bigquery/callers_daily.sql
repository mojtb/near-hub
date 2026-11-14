-- Who calls two contracts, in one read of receipt_actions: the Chain Signatures contract, v1.signer, and NEAR Intents'
-- contract, intents.near.
-- A row is one caller of one of the two contracts on one day: an account among that contract's top @top_n callers by
-- function calls. Nothing below that rank leaves BigQuery.
--   caller_account_id   the account that sent the receipt: a user's own account, a relayer's user, or another contract
--                       that calls this one
--   calls               function calls it made to the contract that day
--   day_calls, day_callers
--                       the contract's totals for the day, repeated on every row: all function calls it received and
--                       the distinct accounts that made them
-- Parameters: @first_day and @last_day, both inclusive, cut the read to those daily partitions; @top_n is the rank kept.
WITH grouped AS (
  SELECT
    block_date,
    receipt_receiver_account_id AS contract_id,
    receipt_predecessor_account_id AS caller_account_id,
    COUNT(*) AS calls
  FROM `bigquery-public-data.crypto_near_mainnet_us.receipt_actions`
  WHERE block_date BETWEEN @first_day AND @last_day
    AND action_kind = 'FUNCTION_CALL'
    AND receipt_receiver_account_id IN ('v1.signer', 'intents.near')
  GROUP BY block_date, contract_id, caller_account_id
),

ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY block_date, contract_id ORDER BY calls DESC, caller_account_id) AS rank_by_calls,
    SUM(calls) OVER (PARTITION BY block_date, contract_id) AS day_calls,
    COUNT(*) OVER (PARTITION BY block_date, contract_id) AS day_callers
  FROM grouped
)

SELECT block_date, contract_id, caller_account_id, calls, rank_by_calls, day_calls, day_callers
FROM ranked
WHERE rank_by_calls <= @top_n
ORDER BY block_date, contract_id, rank_by_calls
