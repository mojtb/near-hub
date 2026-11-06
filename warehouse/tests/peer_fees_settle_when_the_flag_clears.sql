-- Holds fct_peer_daily.is_fee_revenue_provisional to the snapshots, as intents_fees_settle_when_the_flag_clears does for
-- fct_intents_daily. Each row returned is a way the flag is wrong:
--   moved_after_flag_cleared: a figure of NEAR's read at least intents_fee_settle_nights nights after its day ended
--     later moved by over 0.01% in the day's first week. Measure again and raise the var in dbt_project.yml.
--   flag_disagrees_with_reads: on any chain, the flag is not what the newest reads imply.
-- The first check is NEAR's alone. Other chains have no fixed settling time: Ethereum's and Solana's figures have moved
-- after the third read, which the catalog says, so those moves are not a failure.
{% set settle_nights = var('intents_fee_settle_nights') %}

with reads as (
    select p.chain_id, f.data_type, f.date_day, f.snapshot_date, f.value_usd as value
    from {{ ref('stg_defillama__chain_fees') }} f
    join {{ ref('peers') }} p using (llama_chain)
),

rereads as (
    select
        *,
        lag(snapshot_date) over reads_of_a_day as previous_snapshot,
        lag(value) over reads_of_a_day as previous_value
    from reads
    window reads_of_a_day as (partition by chain_id, data_type, date_day order by snapshot_date)
),

implied as (
    select chain_id, date_day, bool_or(newest_read - date_day < {{ settle_nights }}) as is_provisional
    from (
        select chain_id, data_type, date_day, max(snapshot_date) as newest_read
        from reads
        group by chain_id, data_type, date_day
    )
    group by chain_id, date_day
)

select 'moved_after_flag_cleared' as failure, chain_id, data_type, date_day, previous_snapshot, snapshot_date, previous_value, value
from rereads
where chain_id = 'near'
  and previous_snapshot - date_day >= {{ settle_nights }}
  and previous_snapshot - date_day < 7
  and abs(value - previous_value) > 0.0001 * greatest(abs(value), abs(previous_value))

union all

select 'flag_disagrees_with_reads', f.chain_id, null, f.date_day, null, null, null, null
from {{ ref('fct_peer_daily') }} f
left join implied i using (chain_id, date_day)
where f.is_fee_revenue_provisional is distinct from coalesce(i.is_provisional, false)
