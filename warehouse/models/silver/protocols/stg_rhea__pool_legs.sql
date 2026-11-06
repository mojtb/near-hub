-- Point in time: one row per token per Rhea pool, with what the pool holds in the token's smallest unit. Rhea's own tvl
-- prices each side at its listed price, so one pool of two unknown tokens reads $1.37B: use amounts, not tvl, to judge depth.
-- Concentrated-liquidity (DCL) pools are not in this list.
with files as ({{ bronze_files('rhea__top_pools') }}),

pools as (
    select snapshot_date, {{ explode('doc') }} as p from files
),

legs as (
    select
        snapshot_date,
        p->>'id' as pool_id,
        p->>'pool_kind' as pool_kind,
        unnest(from_json(p->'token_account_ids', '["VARCHAR"]')) as token_id,
        unnest(from_json(p->'amounts', '["VARCHAR"]')) as amount_raw
    from pools
)

select *, {{ is_latest('pool_id, token_id') }} as is_latest
from legs
