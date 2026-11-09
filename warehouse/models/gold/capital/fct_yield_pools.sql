-- Yield pools on NEAR, as of each DefiLlama reading. APY values are percentages as DefiLlama reports them.
-- DefiLlama splits APY into base and reward. No NEAR pool has had a reward APY, so base has equalled the total on every
-- row and only the total is kept; removed_columns_would_still_be_empty says when a reward appears and the split matters.
select snapshot_date, pool_id, project, symbol, tvl_usd, apy_pct
from {{ ref('stg_defillama__yield_pools') }}
