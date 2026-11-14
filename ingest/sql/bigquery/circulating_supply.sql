-- NEAR's own daily circulating supply, as its lakehouse computes it and publishes it in the dataset: one row per day,
-- with the block the figure was computed at. The table is small, a few hundred KB, so it is read whole every time.
-- The supplies are in yoctoNEAR (1 NEAR = 10^24) as floating-point numbers.
SELECT
  block_date,
  computed_at_block_height,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', TIMESTAMP_MICROS(DIV(computed_at_block_timestamp, 1000))) AS computed_at_block_utc,
  circulating_tokens_supply,
  total_tokens_supply
FROM `bigquery-public-data.crypto_near_mainnet_us.circulating_supply`
ORDER BY block_date, computed_at_block_height
