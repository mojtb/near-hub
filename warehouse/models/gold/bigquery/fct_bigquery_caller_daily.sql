-- Who called two contracts, counted over every function call in NEAR's public BigQuery dataset: each account among
-- the day's 25 largest callers of the Chain Signatures contract, v1.signer, and of NEAR Intents' contract,
-- intents.near. A caller is the account that sent the receipt: a user's own account, the user a relayer signed for, or
-- another contract. A contract also calls itself, to finish work it started, and those calls are a row of their own.
with rows as (select * from {{ ref('stg_bigquery__callers_daily') }} where is_latest)

select
    r.date_day,
    r.contract_id,
    r.caller_account_id,
    e.entity,
    e.category,
    r.calls,
    r.calls * 1.0 / nullif(r.day_calls, 0) as call_share,
    r.rank_by_calls,
    r.caller_account_id = r.contract_id as is_self_call,
    r.day_calls as contract_calls,
    r.day_callers as contract_callers
from rows r
left join {{ ref('entities') }} e on e.account_id = r.caller_account_id
