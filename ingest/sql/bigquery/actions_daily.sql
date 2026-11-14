-- Actions per UTC day by kind, and each day's largest contracts by function calls, in one read of receipt_actions.
-- An action is one step inside a receipt: a function call, a transfer, an account created or deleted, a key added or
-- removed, a contract deployed, a stake, or a relayed (delegated) request.
-- A row with is_kind_total = 1 is one kind on one day. The other rows are single contracts, for function calls only:
-- those among the day's top @top_n by calls, by distinct signers or by distinct callers. Nothing below that rank leaves
-- BigQuery.
--   signers       distinct accounts that signed the transaction the action came from. For a relayed action that is the
--                 relayer, not the user.
--   predecessors  distinct accounts that sent the receipt. For a relayed action that is the user, so on a contract this
--                 counts the users a relayer signed for; it also counts contracts that call the contract, and 'system',
--                 which sends refunds.
--   receivers     distinct accounts the receipt went to: the contracts called, the accounts created, and so on.
--   from_system   actions in receipts sent by 'system': refunds of unused gas and deposits, which arrive as transfers.
-- Parameters: @first_day and @last_day, both inclusive, cut the read to those daily partitions; @top_n is the rank kept.
WITH actions AS (
  SELECT
    block_date,
    action_kind,
    IF(action_kind = 'FUNCTION_CALL', receipt_receiver_account_id, NULL) AS contract_id,
    receipt_receiver_account_id,
    receipt_predecessor_account_id,
    signer_account_id
  FROM `bigquery-public-data.crypto_near_mainnet_us.receipt_actions`
  WHERE block_date BETWEEN @first_day AND @last_day
),

grouped AS (
  SELECT
    block_date,
    action_kind,
    contract_id,
    GROUPING(contract_id) AS is_kind_total,
    COUNT(*) AS actions,
    COUNT(DISTINCT signer_account_id) AS signers,
    COUNT(DISTINCT receipt_predecessor_account_id) AS predecessors,
    COUNT(DISTINCT receipt_receiver_account_id) AS receivers,
    COUNTIF(receipt_predecessor_account_id = 'system') AS from_system
  FROM actions
  GROUP BY GROUPING SETS ((block_date, action_kind, contract_id), (block_date, action_kind))
),

ranked AS (
  SELECT
    *,
    ROW_NUMBER() OVER (PARTITION BY block_date, is_kind_total ORDER BY actions DESC, contract_id) AS rank_by_calls,
    ROW_NUMBER() OVER (PARTITION BY block_date, is_kind_total ORDER BY signers DESC, contract_id) AS rank_by_signers,
    ROW_NUMBER() OVER (PARTITION BY block_date, is_kind_total ORDER BY predecessors DESC, contract_id) AS rank_by_predecessors
  FROM grouped
  WHERE is_kind_total = 1 OR action_kind = 'FUNCTION_CALL'
)

SELECT
  block_date,
  action_kind,
  is_kind_total,
  IF(is_kind_total = 1, NULL, contract_id) AS contract_id,
  actions,
  signers,
  predecessors,
  receivers,
  from_system,
  IF(is_kind_total = 1, NULL, rank_by_calls) AS rank_by_calls,
  IF(is_kind_total = 1, NULL, rank_by_signers) AS rank_by_signers,
  IF(is_kind_total = 1, NULL, rank_by_predecessors) AS rank_by_predecessors
FROM ranked
WHERE is_kind_total = 1 OR rank_by_calls <= @top_n OR rank_by_signers <= @top_n OR rank_by_predecessors <= @top_n
ORDER BY block_date, is_kind_total DESC, action_kind, rank_by_calls
