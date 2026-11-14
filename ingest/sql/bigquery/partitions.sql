-- Rows per day in every table of the dataset, from BigQuery's own record of each table's daily partitions.
-- The tables are partitioned by block_date, so a partition's row count is that day's count of blocks, transactions,
-- receipts or actions, for the whole history, without reading the tables. Google bills its 10 MB minimum.
-- partition_id is the day as YYYYMMDD; '__NULL__' and '__UNPARTITIONED__' are BigQuery's own buckets and are kept.
SELECT
  table_name,
  partition_id,
  total_rows,
  total_logical_bytes,
  FORMAT_TIMESTAMP('%Y-%m-%dT%H:%M:%SZ', last_modified_time) AS last_modified_utc
FROM `bigquery-public-data.crypto_near_mainnet_us.INFORMATION_SCHEMA.PARTITIONS`
ORDER BY table_name, partition_id
