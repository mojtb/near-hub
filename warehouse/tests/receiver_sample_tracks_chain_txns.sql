-- fct_receiver_sample_daily scales a few sample blocks up to a day. Summed over receivers, a day's estimated
-- transactions should come back to the chain's own count in fct_chain_daily. Measured at the 2026-11-09 pin: 0.68 to
-- 2.04 times the count on 24-block days, 0.87 to 1.09 on 96-block days, and 3% low over all days together. The limits
-- here are wide enough for that noise and narrow enough to catch a sampler that skips blocks or counts them twice.
with days as (
    select date_day, max(blocks_sampled) as blocks_sampled, sum(estimated_daily_txns) as estimated_txns
    from {{ ref('fct_receiver_sample_daily') }}
    group by date_day
),

compared as (
    select d.date_day, d.blocks_sampled, d.estimated_txns, c.txns, d.estimated_txns / nullif(c.txns, 0) as ratio
    from days d
    join {{ ref('fct_chain_daily') }} c using (date_day)
    where c.txns > 0
)

select cast(date_day as varchar) as scope, blocks_sampled, estimated_txns, txns, ratio
from compared
where ratio not between 0.5 and 2.5
   or (blocks_sampled >= 96 and ratio not between 0.75 and 1.25)

union all

select 'all days together', null, sum(estimated_txns), sum(txns), sum(estimated_txns) / sum(txns)
from compared
having sum(estimated_txns) / sum(txns) not between 0.9 and 1.1
