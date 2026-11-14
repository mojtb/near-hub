-- Who signs the day's transactions, and who sends NEAR Intents' contract its transactions, in one read of the
-- transactions table.
-- A row is one signer on one day: an account among the day's top @top_n signers by transactions, or among the top
-- @top_n signers of the transactions sent to intents.near. Nothing below those ranks leaves BigQuery, so no small
-- account is copied out.
--   txns                  transactions the account signed that day
--   receivers             distinct accounts it sent them to. A batch job that writes to very many accounts shows here:
--                         by receiver it is spread too thin to be seen.
--   intents_txns          those of its transactions that were sent to intents.near
--   day_txns, day_intents_txns, day_intents_signers
--                         the day's totals, repeated on every row: all transactions, the transactions sent to
--                         intents.near, and the distinct accounts that signed one of those
-- A signer is the account that signed and paid for the transaction: for a relayed transaction, the relayer.
-- Parameters: @first_day and @last_day, both inclusive, cut the read to those daily partitions; @top_n is the rank kept.
WITH grouped AS (
  SELECT
    block_date,
    signer_account_id,
    COUNT(*) AS txns,
    COUNT(DISTINCT receiver_account_id) AS receivers,
    COUNTIF(receiver_account_id = 'intents.near') AS intents_txns
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date BETWEEN @first_day AND @last_day
  GROUP BY block_date, signer_account_id
),

ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY block_date ORDER BY txns DESC, signer_account_id) AS rank_by_txns,
    ROW_NUMBER() OVER (PARTITION BY block_date ORDER BY intents_txns DESC, signer_account_id) AS rank_by_intents_txns,
    SUM(txns) OVER (PARTITION BY block_date) AS day_txns,
    SUM(intents_txns) OVER (PARTITION BY block_date) AS day_intents_txns,
    COUNTIF(intents_txns > 0) OVER (PARTITION BY block_date) AS day_intents_signers
  FROM grouped
)

SELECT
  block_date,
  signer_account_id,
  txns,
  receivers,
  intents_txns,
  rank_by_txns,
  IF(intents_txns > 0, rank_by_intents_txns, NULL) AS rank_by_intents_txns,
  day_txns,
  day_intents_txns,
  day_intents_signers
FROM ranked
WHERE rank_by_txns <= @top_n OR (intents_txns > 0 AND rank_by_intents_txns <= @top_n)
ORDER BY block_date, rank_by_txns
