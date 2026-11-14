-- Every table and view in NEAR's public dataset: when it last changed, its rows and its size.
-- This reads the dataset's own list of tables, not the tables, so Google bills nothing for it.
-- It answers the first question about this source: is it still being loaded.
SELECT
  table_id AS table_name,
  CASE type WHEN 1 THEN 'table' WHEN 2 THEN 'view' ELSE CAST(type AS STRING) END AS table_type,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', TIMESTAMP_MILLIS(creation_time)) AS created_utc,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', TIMESTAMP_MILLIS(last_modified_time)) AS last_modified_utc,
  row_count,
  size_bytes
FROM `bigquery-public-data.crypto_near_mainnet_us.__TABLES__`
ORDER BY table_id
