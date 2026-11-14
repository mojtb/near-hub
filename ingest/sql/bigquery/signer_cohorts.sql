-- Do accounts come back? Every account that ever signed a transaction is placed in the month it first signed one (its
-- cohort), and counted again in each later month in which it signed at least one. One row per cohort month and active
-- month; the row where the two are equal is the cohort's size.
-- This reads the signer and the day of every transaction since genesis, so it is the largest query here and is run by
-- hand, not every night. Only counts leave BigQuery: no account id is in the result.
-- An account also signs its own deletion, so a cohort includes accounts made and removed by a batch.
-- Parameter: @last_day, inclusive, is the last day read; the month it falls in is not a whole month.
WITH signer_months AS (
  SELECT
    signer_account_id,
    DATE_TRUNC(block_date, MONTH) AS active_month
  FROM `bigquery-public-data.crypto_near_mainnet_us.transactions`
  WHERE block_date <= @last_day
  GROUP BY signer_account_id, active_month
),

with_cohort AS (
  SELECT
    active_month,
    MIN(active_month) OVER (PARTITION BY signer_account_id) AS cohort_month
  FROM signer_months
)

SELECT
  cohort_month,
  active_month,
  COUNT(*) AS signers
FROM with_cohort
GROUP BY cohort_month, active_month
ORDER BY cohort_month, active_month
