-- Which contracts the day's function calls went to, counted over every action receipt in NEAR's public BigQuery
-- dataset: each contract among the day's 25 largest by calls, by distinct signers or by distinct callers.
-- signers are the accounts that signed the transaction a call came from; for a relayed call that is the relayer.
-- callers are the accounts that sent the receipt; for a relayed call that is the user, so callers is the count that
-- sees an application's users when a relayer pays for them. It also counts other contracts calling this one.
-- Shares are of the day's function calls and of the day's distinct signers and callers of any function call.
with rows as (select * from {{ ref('stg_bigquery__actions_daily') }} where is_latest),

day as (select date_day, actions, signers, predecessors from rows where is_kind_total and action_kind = 'FUNCTION_CALL')

select
    r.date_day,
    r.contract_id,
    e.entity,
    e.category,
    r.actions as function_calls,
    r.signers,
    r.predecessors as callers,
    r.actions * 1.0 / nullif(day.actions, 0) as call_share,
    r.signers * 1.0 / nullif(day.signers, 0) as signer_share,
    r.predecessors * 1.0 / nullif(day.predecessors, 0) as caller_share,
    r.rank_by_calls,
    r.rank_by_signers,
    r.rank_by_predecessors as rank_by_callers
from rows r
join day using (date_day)
left join {{ ref('entities') }} e on e.account_id = r.contract_id
where not r.is_kind_total
