-- What the chain did each UTC day, by kind of action, counted over every action receipt in NEAR's public BigQuery
-- dataset: function calls, transfers, accounts created and deleted, keys added and removed, contracts deployed, stakes,
-- relayed (delegated) requests, and the newer kinds for global contracts and state initialisation. Accounts deleted and
-- contracts deployed are counts NearBlocks stops serving when it switches /v1 off on 2026-11-22.
select
    date_day,
    action_kind,
    actions,
    signers,
    predecessors,
    receivers,
    from_system,
    actions - from_system as actions_not_from_system
from {{ ref('stg_bigquery__actions_daily') }}
where is_latest and is_kind_total
