-- Who signed the day's transactions, counted over every transaction in NEAR's public BigQuery dataset: each account
-- among the day's 25 largest signers by transactions, or among the 25 largest signers of the transactions sent to
-- NEAR Intents' contract. fct_bigquery_receiver_daily counts the same transactions by who received them.
-- A signer is the account that signed and paid for a transaction, so a relayer or a batch job is one row here however
-- many accounts it writes to. That is what receivers shows: a job that writes to two million accounts cannot be seen
-- by receiver, and is the largest row by signer.
with rows as (select * from {{ ref('stg_bigquery__signers_daily') }} where is_latest)

select
    r.date_day,
    r.signer_account_id,
    e.entity,
    e.category,
    r.txns,
    r.receivers,
    r.txns * 1.0 / nullif(r.day_txns, 0) as txn_share,
    case when r.rank_by_txns <= 25 then r.rank_by_txns end as rank_by_txns,
    r.intents_txns,
    r.intents_txns * 1.0 / nullif(r.day_intents_txns, 0) as intents_txn_share,
    r.rank_by_intents_txns,
    r.day_txns,
    r.day_intents_txns,
    r.day_intents_signers
from rows r
left join {{ ref('entities') }} e on e.account_id = r.signer_account_id
