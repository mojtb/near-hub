-- Decentralization per epoch. nakamoto_33 is the fewest validators whose stake exceeds one third,
-- the share that can halt finality. nakamoto_67 is the fewest exceeding two thirds.
with ranked as (
    select
        epoch_height,
        epoch_start_height,
        stake_near,
        stake_share,
        stake_rank,
        sum(stake_share) over (partition by epoch_height order by stake_rank) as cumulative_share
    from {{ ref('fct_validator_epoch') }}
),

summary as (
    select
        epoch_height,
        min(epoch_start_height) as epoch_start_height,
        count(*) as validators,
        sum(stake_near) as total_stake_near,
        max(stake_share) as top_validator_share,
        sum(stake_share) filter (where stake_rank <= 10) as top_10_share,
        sum(stake_share * stake_share) as stake_hhi,
        min(stake_rank) filter (where cumulative_share > 1.0 / 3) as nakamoto_33,
        min(stake_rank) filter (where cumulative_share > 2.0 / 3) as nakamoto_67
    from ranked
    group by epoch_height
)

-- Date and supply come from the nearest earlier daily block, and stay empty if that block is over a day away.
select
    s.*,
    case when s.epoch_start_height - b.block_height <= 200000 then b.date_day end as approx_date_day,
    case when s.epoch_start_height - b.block_height <= 200000 then b.total_supply_near end as total_supply_near,
    case when s.epoch_start_height - b.block_height <= 200000
        then s.total_stake_near / nullif(b.total_supply_near, 0) end as staking_ratio
from summary s
asof left join {{ ref('dim_block_day') }} b on s.epoch_start_height >= b.block_height
