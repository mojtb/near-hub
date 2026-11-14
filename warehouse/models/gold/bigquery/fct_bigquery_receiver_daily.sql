-- Who the day's transactions were sent to, counted over every transaction in NEAR's public BigQuery dataset: each
-- account among the day's 25 largest receivers by transactions or by distinct signers. fct_receiver_sample_daily
-- estimates the same split from about one block in a thousand; this is the full count for the days BigQuery was read.
-- A receiver is the account a transaction is addressed to. When a relayer signs for a user the transaction is addressed
-- to the user's own account, so an application used through a relayer shows up here as the relayer's many receivers,
-- not as one contract: fct_bigquery_contract_daily counts by the contract called.
with rows as (select * from {{ ref('stg_bigquery__transactions_daily') }} where is_latest),

day as (select date_day, txns, signers from rows where is_day_total)

select
    r.date_day,
    r.receiver_account_id,
    e.entity,
    e.category,
    r.txns,
    r.signers,
    r.txns * 1.0 / nullif(day.txns, 0) as txn_share,
    r.signers * 1.0 / nullif(day.signers, 0) as signer_share,
    r.rank_by_txns,
    r.rank_by_signers
from rows r
join day using (date_day)
left join {{ ref('entities') }} e on e.account_id = r.receiver_account_id
where not r.is_day_total
