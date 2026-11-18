-- fct_receiver_sample_daily scales a few sample blocks up to a day. Summed over receivers, a day's estimated
-- transactions should come back to the chain's own count in fct_chain_daily. Measured at the 2026-11-09 pin, over 162
-- days of 24 blocks: 0.68 to 2.04 times the count, 0.87 to 1.09 on 96-block days, and 3% low over all days together.
-- Once the sample reached a full year (354 days of 24 blocks, on 2026-11-10) the range was 0.46 to 2.44, with five days
-- under 0.5 and all days together 2% low. So one 24-block day may be up to three times off either way.
-- At the 2026-11-18 snapshot, 19 days of 96 blocks read 0.82 to 1.25 (standard deviation 0.095, against 0.248 at 24
-- blocks), and 2026-11-17 read 1.252, past the band of 0.75 to 1.25 this test first had. Four times the blocks halves
-- the spread, so halving the year's worst 24-block days says a sound 96-block day can still read about 0.68 to 1.56.
-- One 96-block day is therefore held to 0.6 to 1.6, which still catches a day counted twice or half skipped. Noise
-- averages out over a week: every run of seven 96-block days read 0.93 to 0.99, so seven in a row are held to 0.8 to
-- 1.2, which catches a fault that began recently before it can move the whole history. A sampler that skips blocks or
-- counts them twice on most days moves the total, and the last check catches that.
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
),

weeks as (
    select
        date_day,
        sum(estimated_txns) over seven as estimated_txns,
        sum(txns) over seven as txns,
        count(*) over seven as days_in_window,
        min(blocks_sampled) over seven as fewest_blocks
    from compared
    window seven as (order by date_day rows between 6 preceding and current row)
)

select cast(date_day as varchar) as scope, blocks_sampled, estimated_txns, txns, ratio
from compared
where ratio not between 0.33 and 3.0
   or (blocks_sampled >= 96 and ratio not between 0.6 and 1.6)

union all

select 'seven days to ' || cast(date_day as varchar), fewest_blocks, estimated_txns, txns, estimated_txns / txns
from weeks
where days_in_window = 7 and fewest_blocks >= 96 and estimated_txns / txns not between 0.8 and 1.2

union all

select 'all days together', null, sum(estimated_txns), sum(txns), sum(estimated_txns) / sum(txns)
from compared
having sum(estimated_txns) / sum(txns) not between 0.9 and 1.1
