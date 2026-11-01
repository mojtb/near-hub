-- Yield pools on NEAR, as of each DefiLlama reading. APY values are percentages as DefiLlama reports them.
select snapshot_date, pool_id, project, symbol, tvl_usd, apy_pct, apy_base_pct, apy_reward_pct
from {{ ref('stg_defillama__yield_pools') }}
