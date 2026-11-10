-- MPC operators as NearBlocks reports them, per snapshot: the list and each node's address. The operator list and threshold
-- are the contract's, in fct_mpc_participants and fct_mpc_state; a test holds NearBlocks' list to the contract's as read
-- the same night, and dq_reconciliation its threshold. NearBlocks also serves is_validator and three TEE fields, which have never held a
-- value (false, none and empty on every read), so they stay in silver; removed_columns_would_still_be_empty says when
-- that changes.
select snapshot_date, operator_account_id, node_url
from {{ ref('stg_nearblocks__mpc_operators') }}
