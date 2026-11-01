-- Every transfer touching a crawled wallet. `amount` is signed from the wallet's point of view.
-- Pages overlap on purpose at the crawl's tail, so rows are made unique here.
with files as ({{ bronze_files('fastnear__transfers') }}),

rows as (
    select snapshot_date, {{ explode("doc->'transfers'") }} as t from files
),

typed as (
    select
        snapshot_date,
        t->>'account_id' as account_id,
        t->>'other_account_id' as counterparty_id,
        cast(t->>'block_height' as bigint) as block_height,
        cast(t->>'block_timestamp' as hugeint) as block_timestamp_ns,
        {{ unix_day("cast(t->>'block_timestamp' as hugeint) // 1000000000") }} as date_day,
        t->>'transaction_id' as transaction_id,
        t->>'receipt_id' as receipt_id,
        cast(t->>'action_index' as integer) as action_index,
        cast(t->>'log_index' as integer) as log_index,
        cast(t->>'transfer_index' as bigint) as transfer_index,
        t->>'signer_id' as signer_id,
        t->>'predecessor_id' as predecessor_id,
        t->>'asset_id' as asset_id,
        t->>'asset_type' as asset_type,
        t->>'transfer_type' as transfer_type,
        t->>'method_name' as method_name,
        t->>'amount' as amount_raw,
        cast(t->>'human_amount' as double) as amount_token,
        cast(t->>'usd_amount' as double) as amount_usd,
        t->>'end_of_block_balance' as end_of_block_balance_raw
    from rows
)

select *
from typed
qualify row_number() over (
    partition by account_id, block_height, transaction_id, receipt_id, action_index, log_index, transfer_index, asset_id, amount_raw
    order by snapshot_date desc
) = 1
