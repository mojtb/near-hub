-- The Bitwise NEAR ETF's flows set against what the chain issued and what the revenue wallets took in, from the fund's
-- first day. One row per trading day. The seed baskets of 2026-09-28 are left out of the flow, as in fct_etf_nrr_daily's
-- flow_basis; a creation is NEAR delivered to the trust, which need not have been bought on the market that day.
with fund as (
    select date_day, case when flow_basis <> 'seed_capital' then flow_near end as flow_near,
        case when flow_basis <> 'seed_capital' then flow_usd end as flow_usd
    from {{ ref('fct_etf_nrr_daily') }}
),

launch as (select min(date_day) as first_day from fund),

chain as (
    select
        s.date_day,
        sum(s.minted_near) over (order by s.date_day) as cumulative_minted_near,
        sum(coalesce(i.received_near, 0)) over (order by s.date_day) as cumulative_revenue_inflow_near
    from {{ ref('fct_supply_daily') }} s
    cross join launch l
    left join (select date_day, sum(received_near) as received_near from {{ ref('fct_revenue_inflows_daily') }} group by 1) i using (date_day)
    where s.date_day >= l.first_day
),

running as (
    select date_day, flow_near, flow_usd, sum(coalesce(flow_near, 0)) over (order by date_day) as cumulative_flow_near
    from fund
)

select
    r.date_day,
    r.cumulative_flow_near,
    c.cumulative_minted_near,
    c.cumulative_revenue_inflow_near,
    r.cumulative_flow_near / nullif(c.cumulative_minted_near, 0) as cumulative_flow_to_issuance_ratio,
    r.flow_near / nullif(s.minted_near, 0) as flow_to_issuance_ratio,
    r.flow_usd / nullif(m.reported_spot_volume_usd, 0) as flow_share_of_spot_volume
from running r
join chain c using (date_day)
join {{ ref('fct_supply_daily') }} s using (date_day)
left join {{ ref('fct_market_daily') }} m using (date_day)
