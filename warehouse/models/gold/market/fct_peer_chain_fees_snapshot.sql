-- Each chain's own row in DefiLlama's fee and revenue lists (category Chain), as of each reading: the transaction
-- fees users paid the chain, and the part DefiLlama books as the chain's revenue, which is what the chain burns or
-- keeps. It is the only figure the warehouse holds for what reaches a peer's token, and it is thin: one row per
-- night from 2026-11-01. A chain whose 30-day revenue moved more than twofold across the stored readings is flagged,
-- because a 30-day sum cannot move that far in a few nights unless the source rewrote it.
-- NEAR's row is DefiLlama's own rule, 70% of gas, which stopped being true on 2026-11-04 when all gas began to
-- burn; NEAR's burn read from the chain is fct_supply_daily.burn_near.
with own as (
    select
        s.snapshot_date,
        p.chain_id,
        max(s.total_24h_usd) filter (where s.data_type = 'dailyFees') as gas_fees_24h_usd,
        max(s.total_7d_usd) filter (where s.data_type = 'dailyFees') as gas_fees_7d_usd,
        max(s.total_30d_usd) filter (where s.data_type = 'dailyFees') as gas_fees_30d_usd,
        max(s.total_1y_usd) filter (where s.data_type = 'dailyFees') as gas_fees_1y_usd,
        max(s.total_24h_usd) filter (where s.data_type = 'dailyRevenue') as chain_revenue_24h_usd,
        max(s.total_7d_usd) filter (where s.data_type = 'dailyRevenue') as chain_revenue_7d_usd,
        max(s.total_30d_usd) filter (where s.data_type = 'dailyRevenue') as chain_revenue_30d_usd,
        max(s.total_1y_usd) filter (where s.data_type = 'dailyRevenue') as chain_revenue_1y_usd
    from {{ ref('stg_defillama__chain_fee_protocols') }} s
    join {{ ref('peers') }} p using (llama_chain)
    where s.category = 'Chain'
    group by 1, 2
),

spread as (
    select chain_id, max(chain_revenue_30d_usd) / nullif(min(chain_revenue_30d_usd), 0) as highest_over_lowest
    from own
    where chain_revenue_30d_usd is not null
    group by 1
)

select
    o.snapshot_date,
    o.chain_id,
    o.gas_fees_24h_usd,
    o.gas_fees_7d_usd,
    o.gas_fees_30d_usd,
    o.gas_fees_1y_usd,
    o.chain_revenue_24h_usd,
    o.chain_revenue_7d_usd,
    o.chain_revenue_30d_usd,
    o.chain_revenue_1y_usd,
    o.chain_revenue_30d_usd / nullif(o.gas_fees_30d_usd, 0) as revenue_share_of_gas_30d,
    c.market_cap_usd as market_cap_day_before_usd,
    c.market_cap_usd / nullif(o.chain_revenue_30d_usd * 365 / 30, 0) as multiple_on_chain_revenue,
    s.highest_over_lowest as revenue_30d_highest_over_lowest,
    coalesce(s.highest_over_lowest > 2, false) as is_unstable
from own o
left join spread s using (chain_id)
left join {{ ref('fct_peer_daily') }} c on c.chain_id = o.chain_id and c.date_day = o.snapshot_date - 1
