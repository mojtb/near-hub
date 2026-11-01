-- TVL on NEAR per protocol per day from DefiLlama. Exchange wallets are excluded; DefiLlama also leaves
-- them out of its chain TVL. Liquid staking and lending can double-count the same NEAR.
with cex as (
    select protocol_slug from {{ ref('stg_defillama__protocols') }}
    where is_latest and category = 'CEX'
)

select
    t.date_day,
    t.protocol_slug,
    p.protocol_name,
    p.category,
    t.tvl_usd
from {{ ref('stg_defillama__protocol_tvl') }} t
left join {{ ref('stg_defillama__protocols') }} p on p.protocol_slug = t.protocol_slug and p.is_latest
where t.is_latest and t.protocol_slug not in (select protocol_slug from cex)
