-- The Bitwise NEAR ETF's flows set against what the chain issued and what the revenue wallets took in, from the fund's
-- first trading day. One row per trading day. The seed baskets of 2026-09-28 are left out of the flow, as in
-- fct_etf_nrr_daily's flow_basis, and the seed day is left out of the rows, so the flow and the issuance both start on
-- the first day a share could be bought. A creation is NEAR delivered to the trust, which need not have been bought on
-- the market that day. The 30-day columns count the fund's flow on the trading days inside the window and the issuance
-- on all 30 calendar days, and are empty until the fund has traded for 30 days.
with fund as (
    select date_day, flow_near, flow_usd
    from {{ ref('fct_etf_nrr_daily') }}
    where flow_basis <> 'seed_capital'
),

launch as (select min(date_day) as first_day from fund),

chain as (
    select
        s.date_day,
        s.minted_near,
        sum(s.minted_near) over (order by s.date_day) as cumulative_minted_near,
        sum(coalesce(i.received_near, 0)) over (order by s.date_day) as cumulative_revenue_inflow_near,
        sum(s.minted_near) over (order by s.date_day rows between 29 preceding and current row) as minted_30d_near,
        count(*) over (order by s.date_day rows between 29 preceding and current row) as days_in_window
    from {{ ref('fct_supply_daily') }} s
    cross join launch l
    left join (select date_day, sum(received_near) as received_near from {{ ref('fct_revenue_inflows_daily') }} group by 1) i using (date_day)
    where s.date_day >= l.first_day
),

running as (
    select
        f.date_day,
        f.flow_near,
        f.flow_usd,
        sum(coalesce(f.flow_near, 0)) over (order by f.date_day) as cumulative_flow_near,
        (select sum(g.flow_near) from fund g where g.date_day > f.date_day - 30 and g.date_day <= f.date_day) as flow_30d_near
    from fund f
)

select
    r.date_day,
    r.cumulative_flow_near,
    c.cumulative_minted_near,
    c.cumulative_revenue_inflow_near,
    r.cumulative_flow_near / nullif(c.cumulative_minted_near, 0) as cumulative_flow_to_issuance_ratio,
    r.flow_near / nullif(c.minted_near, 0) as flow_to_issuance_ratio,
    r.flow_usd / nullif(m.reported_spot_volume_usd, 0) as flow_share_of_spot_volume,
    case when c.days_in_window = 30 then r.flow_30d_near end as flow_30d_near,
    case when c.days_in_window = 30 then c.minted_30d_near end as minted_30d_near,
    case when c.days_in_window = 30 then r.flow_30d_near / nullif(c.minted_30d_near, 0) end as flow_to_issuance_30d_ratio
from running r
join chain c using (date_day)
left join {{ ref('fct_market_daily') }} m using (date_day)
