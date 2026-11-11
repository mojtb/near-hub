-- fct_receiver_sample_daily scales a few sample blocks up to a day. Summed over receivers, a day's estimated
-- transactions should come back to the chain's own count in fct_chain_daily. Measured at the 2026-11-09 pin, over 162
-- days of 24 blocks: 0.68 to 2.04 times the count, 0.87 to 1.09 on 96-block days, and 3% low over all days together.
-- Once the sample reached a full year (354 days of 24 blocks, on 2026-11-10) the range was 0.46 to 2.44, with five days
-- under 0.5 and all days together 2% low. So one 24-block day may be up to three times off either way. A sampler that
-- skips blocks or counts them twice on most days moves the total, and the last check catches that.
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
where ratio not between 0.33 and 3.0
   or (blocks_sampled >= 96 and ratio not between 0.75 and 1.25)

union all

select 'all days together', null, sum(estimated_txns), sum(txns), sum(estimated_txns) / sum(txns)
from compared
having sum(estimated_txns) / sum(txns) not between 0.9 and 1.1
