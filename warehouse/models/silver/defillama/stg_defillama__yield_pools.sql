-- Point in time: one row per pool per snapshot.
with files as ({{ bronze_files('defillama__yield_pools') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as p from files
)

select
    snapshot_date,
    p->>'pool' as pool_id,
    p->>'project' as project,
    p->>'symbol' as symbol,
    cast(p->>'tvlUsd' as double) as tvl_usd,
    cast(p->>'apy' as double) as apy_pct,
    cast(p->>'apyBase' as double) as apy_base_pct,
    cast(p->>'apyReward' as double) as apy_reward_pct,
    {{ is_latest("p->>'pool'") }} as is_latest
from rows
