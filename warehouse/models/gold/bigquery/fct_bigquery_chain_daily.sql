-- The chain per UTC day as counted in NEAR's public BigQuery dataset, the source the hackathon's sample prompt names.
-- Blocks come from its blocks table since genesis; transactions, signers and receivers from its transactions table,
-- from a later day because that read is billed by size; the three *_table_rows columns are BigQuery's own count of
-- rows in each table's daily partition, which costs nothing to read and covers every day.
-- This table stands beside fct_chain_daily, which takes the same measures from NearBlocks: dq_reconciliation holds the
-- two against each other day for day. A signer here is the account that signed and paid for a transaction, so a user
-- whose transaction a relayer signs is not counted; fct_bigquery_contract_daily counts those users where they call.
with blocks as (select * from {{ ref('stg_bigquery__blocks_daily') }} where is_latest),

txns as (select * from {{ ref('stg_bigquery__transactions_daily') }} where is_latest and is_day_total),

parts as (
    select
        date_day,
        max(case when table_name = 'transactions' then total_rows end) as transactions_table_rows,
        max(case when table_name = 'receipt_details' then total_rows end) as receipt_details_table_rows,
        max(case when table_name = 'receipt_actions' then total_rows end) as receipt_actions_table_rows
    from {{ ref('stg_bigquery__partitions') }}
    where is_latest and date_day is not null
    group by date_day
),

days as (
    select date_day from blocks
    union
    select date_day from txns
    union
    select date_day from parts
)

select
    d.date_day,
    b.blocks,
    b.first_block_height,
    b.last_block_height,
    b.last_block_at,
    -- A block comes about every 0.6 seconds, so a day whose last block is a minute or more before midnight was still
    -- being loaded when it was read.
    coalesce(b.last_block_at >= cast(d.date_day as timestamp) + interval '1439 minutes', false) as is_day_complete,
    b.block_producers,
    b.total_supply_near,
    t.txns,
    t.signers,
    t.receivers,
    p.transactions_table_rows,
    p.receipt_details_table_rows,
    p.receipt_actions_table_rows
from days d
left join blocks b using (date_day)
left join txns t using (date_day)
left join parts p using (date_day)
