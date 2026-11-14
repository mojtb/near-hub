-- Blocks per UTC day: how many, the first and last height and time, the total supply at the day's last block and how
-- many accounts produced a block. The last block's time shows whether a day is fully loaded: a day whose last block
-- is well before midnight is still arriving.
-- Parameters: @first_day and @last_day, both inclusive, cut the read to those daily partitions.
SELECT
  block_date,
  COUNT(*) AS blocks,
  MIN(block_height) AS first_block_height,
  MAX(block_height) AS last_block_height,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', MIN(block_timestamp_utc)) AS first_block_utc,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', MAX(block_timestamp_utc)) AS last_block_utc,
  CAST(MAX_BY(total_supply, block_height) AS STRING) AS total_supply_yocto,
  COUNT(DISTINCT author_account_id) AS block_producers
FROM `bigquery-public-data.crypto_near_mainnet_us.blocks`
WHERE block_date BETWEEN @first_day AND @last_day
GROUP BY block_date
ORDER BY block_date
