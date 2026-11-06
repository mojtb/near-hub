-- TVL on NEAR per protocol per day from DefiLlama. Exchange wallets are excluded; DefiLlama also leaves
-- them out of its chain TVL. Liquid staking and lending can double-count the same NEAR.
-- A protocol is one DefiLlama id, shown under its newest slug. A protocol missing from the newest reading keeps
-- its history: a missed night and a delisting look the same, and neither is a reason to lose the days already read.
with protocols as (
    select * from {{ ref('stg_defillama__protocols') }} where is_latest
)

select
    t.date_day,
    t.protocol_id,
    p.protocol_slug,
    p.protocol_name,
    p.category,
    t.tvl_usd
from {{ ref('stg_defillama__protocol_tvl') }} t
left join protocols p on p.protocol_id = t.protocol_id
where t.is_latest and p.category is distinct from 'CEX'
