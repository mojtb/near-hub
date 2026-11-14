-- NEAR's own daily circulating supply, as its lakehouse computes it and publishes it in its public BigQuery dataset.
-- It stands beside fct_circulating_supply_daily, which this warehouse builds from every lockup contract read on chain:
-- two computations of the same figure by different hands, held against each other in dq_reconciliation.
-- On some days NEAR's table reports a circulating supply of zero. That is a fault in the table, not a reading, so those
-- days keep their row and total supply, carry no circulating figure, and are marked.
-- Where the table holds a day more than once, the row computed at the highest block is kept.
select
    date_day,
    nullif(circulating_supply_near, 0) as circulating_supply_near,
    total_supply_near,
    nullif(circulating_supply_near, 0) / nullif(total_supply_near, 0) as circulating_share_of_total,
    total_supply_near - nullif(circulating_supply_near, 0) as not_circulating_near,
    circulating_supply_near = 0 as is_zero_in_source,
    computed_at_block_height,
    computed_at
from {{ ref('stg_bigquery__circulating_supply') }}
where is_latest
qualify row_number() over (partition by date_day order by computed_at_block_height desc) = 1
