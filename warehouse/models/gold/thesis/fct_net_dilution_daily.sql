-- How much a holder is diluted, how a staker is paid and how much of issuance comes back, over the 30 days ending on
-- each day. Issuance arrives per epoch and revenue is swept in lumps, so a single day says little: every figure here
-- is a 30-day sum or a rate built from one. Rates are annualized by 365/30.
with inflows as (
    select date_day, sum(received_near) as inflow_near, sum(received_usd) as inflow_usd
    from {{ ref('fct_revenue_inflows_daily') }}
    group by 1
),

-- Epochs are sampled: at most two a day, and before 2025-10 only 5 to 15 days a month have one. Stake moves by a few
-- percent within a month, so it is averaged over the days that have a reading, and a window needs at least five.
stake as (
    select approx_date_day as date_day, avg(total_stake_near) as total_stake_near
    from {{ ref('fct_validator_summary') }}
    where approx_date_day is not null
    group by 1
),

days as (
    select
        s.date_day,
        s.total_supply_near,
        s.minted_near,
        s.burn_near,
        s.treasury_reward_near,
        s.contract_gas_reward_rate,
        coalesce(i.inflow_near, 0) as inflow_near,
        coalesce(i.inflow_usd, 0) as inflow_usd,
        s.minted_near * m.price_usd as minted_usd,
        st.total_stake_near
    from {{ ref('fct_supply_daily') }} s
    left join inflows i using (date_day)
    left join {{ ref('fct_market_daily') }} m using (date_day)
    left join stake st using (date_day)
),

windows as (
    select
        date_day,
        count(*) over w as days_in_window,
        sum(minted_near) over w as minted_30d_near,
        sum(burn_near) over w as burn_30d_near,
        sum(inflow_near) over w as revenue_inflow_30d_near,
        sum(treasury_reward_near) over w as treasury_reward_30d_near,
        sum(inflow_usd) over w as revenue_inflow_30d_usd,
        sum(minted_usd) over w as minted_30d_usd,
        count(minted_usd) over w as priced_days,
        avg(total_supply_near) over w as mean_supply_near,
        avg(total_stake_near) over w as mean_stake_near,
        count(total_stake_near) over w as stake_days,
        max(contract_gas_reward_rate) over w as highest_rebate_rate
    from days
    window w as (order by date_day rows between 29 preceding and current row)
)

select
    date_day,
    minted_30d_near,
    burn_30d_near,
    revenue_inflow_30d_near,
    minted_30d_near - burn_30d_near - revenue_inflow_30d_near as net_issuance_30d_near,
    (burn_30d_near + revenue_inflow_30d_near) / nullif(minted_30d_near, 0) as offset_share,
    minted_30d_near * 365 / 30 / mean_supply_near as gross_inflation_rate,
    (minted_30d_near - burn_30d_near - revenue_inflow_30d_near) * 365 / 30 / mean_supply_near as net_inflation_rate,
    case when stake_days >= 5 then (minted_30d_near - treasury_reward_30d_near) * 365 / 30 / mean_stake_near end as nominal_staking_yield_rate,
    case when stake_days >= 5
        then (minted_30d_near - treasury_reward_30d_near) * 365 / 30 / mean_stake_near - minted_30d_near * 365 / 30 / mean_supply_near
    end as real_staking_yield_rate,
    case when stake_days >= 5 then mean_stake_near / mean_supply_near end as staked_share,
    case when priced_days = 30 then minted_30d_usd end as minted_30d_usd,
    revenue_inflow_30d_usd,
    highest_rebate_rate > 0 as is_burn_lower_bound
from windows
where days_in_window = 30
