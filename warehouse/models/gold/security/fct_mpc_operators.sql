-- MPC operators as NearBlocks reports them, per snapshot. Compare with fct_mpc_participants, read from the contract.
select snapshot_date, operator_account_id, threshold, is_validator, tee_status, tee_expiry, tee_image_hash, node_url
from {{ ref('stg_nearblocks__mpc_operators') }}
