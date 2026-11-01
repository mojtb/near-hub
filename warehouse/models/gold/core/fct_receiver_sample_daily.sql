-- Who the activity is for, estimated from evenly spaced sample blocks. Shares are of the sample that day.
with sample as (
    select * from {{ ref('stg_neardata__receiver_sample') }}
)

select
    s.date_day,
    s.account_id,
    e.entity,
    e.category,
    s.txns as sampled_txns,
    s.receipts as sampled_receipts,
    s.distinct_signers as sampled_distinct_signers,
    s.txns * 1.0 / nullif(s.txns_sampled, 0) as txn_share,
    s.receipts * 1.0 / nullif(s.receipts_sampled, 0) as receipt_share,
    s.receipts * 1.0 * s.blocks_in_day / nullif(s.blocks_sampled, 0) as estimated_daily_receipts,
    s.txns * 1.0 * s.blocks_in_day / nullif(s.blocks_sampled, 0) as estimated_daily_txns,
    s.tokens_burnt_near as sampled_tokens_burnt_near,
    s.blocks_sampled,
    s.blocks_in_day
from sample s
left join {{ ref('entities') }} e using (account_id)
