-- Transactions with the known batch streams taken out, so usage can be read across the break of 2026-04-02, and with
-- the Sweat relayer taken out as well, since Sweat Wallet ends on 2026-12-30. The streams are counted from NearBlocks'
-- per-account statistics, which reach back 365 active days from their first read, so each series starts where its
-- accounts' statistics do and is empty before.
with streams as (
    select
        date_day,
        sum(txns) filter (where account_id in ('hotwallet.kaiching', 'users.kaiching', 'sweat-migration.near')) as batch_stream_txns,
        sum(txns) filter (where account_id = 'sweat-relayer.near') as sweat_relayer_txns
    from {{ ref('fct_contract_daily') }}
    where account_id in ('hotwallet.kaiching', 'users.kaiching', 'sweat-migration.near', 'sweat-relayer.near')
    group by 1
),

-- sweat-migration.near ran for three weeks, so it does not set the start; the two Kai-Ching accounts and the relayer do.
coverage as (
    select
        greatest(min(date_day) filter (where account_id = 'hotwallet.kaiching'), min(date_day) filter (where account_id = 'users.kaiching')) as batch_from,
        min(date_day) filter (where account_id = 'sweat-relayer.near') as sweat_from
    from {{ ref('fct_contract_daily') }}
),

sample as (
    select date_day, sum(sampled_tokens_burnt_near) filter (where entity = 'Sweat Economy') / nullif(sum(sampled_tokens_burnt_near), 0) as sweat_gas_burn_share
    from {{ ref('fct_receiver_sample_daily') }}
    group by 1
),

days as (
    select
        c.date_day,
        c.txns,
        c.txn_fee_near,
        m.price_usd,
        -- fct_contract_daily holds active days only, so a day without a row inside the covered span is a day with none.
        case when c.date_day >= v.batch_from then coalesce(s.batch_stream_txns, 0) end as batch_stream_txns,
        case when c.date_day >= v.sweat_from then coalesce(s.sweat_relayer_txns, 0) end as sweat_relayer_txns,
        sa.sweat_gas_burn_share
    from {{ ref('fct_chain_daily') }} c
    cross join coverage v
    left join streams s using (date_day)
    left join sample sa using (date_day)
    left join {{ ref('fct_market_daily') }} m using (date_day)
    where c.date_day >= v.batch_from and c.txns is not null
)

select
    date_day,
    batch_stream_txns,
    sweat_relayer_txns,
    txns - batch_stream_txns as txns_ex_batch_streams,
    txns - batch_stream_txns - sweat_relayer_txns as txns_ex_batch_streams_and_sweat,
    sweat_relayer_txns / nullif(txns - batch_stream_txns, 0) as sweat_share_of_txns_ex_batch_streams,
    txn_fee_near * price_usd as txn_fee_usd,
    txn_fee_near / nullif(txns, 0) as txn_fee_per_txn_near,
    sweat_gas_burn_share,
    date_day < date '2026-04-03' as is_before_usage_break
from days
