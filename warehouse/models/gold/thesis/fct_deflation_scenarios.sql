-- How much Intents volume it would take for NEAR's supply to stop growing, under today's issuance and under the end
-- state of HSP-029, at several shares of fees kept. Everything is measured over the 30 days ending on as_of_date, the
-- newest day whose fees are settled. Revenue is in dollars and issuance in NEAR, so the answer moves with the price:
-- break-even volume rises in step with price_usd and falls in step with fee_rate, and a reader can rescale it.
with as_of as (
    select max(date_day) as as_of_date from {{ ref('fct_intents_daily') }} where not is_fee_revenue_provisional
),

supply as (
    select d.date_day as as_of_date, d.minted_30d_near / 30 as minted_near_per_day, d.burn_30d_near / 30 as burn_near_per_day,
        d.minted_30d_near * 365 / 30 / d.gross_inflation_rate as mean_supply_near
    from {{ ref('fct_net_dilution_daily') }} d
    join as_of a on d.date_day = a.as_of_date
),

intents as (
    select
        avg(i.volume_usd) as volume_usd_per_day,
        sum(i.fees_usd) / sum(i.volume_usd) as fee_rate,
        sum(i.revenue_usd) / sum(i.fees_usd) as capture_rate
    from {{ ref('fct_intents_daily') }} i, as_of a
    where i.date_day > a.as_of_date - 30 and i.date_day <= a.as_of_date
),

price as (
    select m.price_usd from {{ ref('fct_market_daily') }} m join as_of a on m.date_day = a.as_of_date
),

capture_cases as (
    select * from (values ('measured', cast(null as double)), ('at_50_pct', 0.5), ('at_70_pct', 0.7), ('at_100_pct', 1.0)) t(capture_case, capture_rate)
),

grid as (
    select
        s.as_of_date,
        r.scenario_id,
        c.capture_case,
        coalesce(r.annual_issuance_rate * s.mean_supply_near / 365, s.minted_near_per_day) as issuance_near_per_day,
        s.burn_near_per_day,
        s.mean_supply_near,
        p.price_usd,
        i.fee_rate,
        coalesce(c.capture_rate, i.capture_rate) as capture_rate,
        i.volume_usd_per_day
    from supply s
    cross join {{ ref('issuance_scenarios') }} r
    cross join capture_cases c
    cross join intents i
    cross join price p
)

select
    as_of_date,
    scenario_id,
    capture_case,
    issuance_near_per_day,
    burn_near_per_day,
    price_usd,
    fee_rate,
    capture_rate,
    volume_usd_per_day,
    (issuance_near_per_day - burn_near_per_day) * price_usd / (fee_rate * capture_rate) as breakeven_volume_usd_per_day,
    (issuance_near_per_day - burn_near_per_day) * price_usd / (fee_rate * capture_rate) / volume_usd_per_day as breakeven_volume_multiple,
    (issuance_near_per_day - burn_near_per_day - volume_usd_per_day * fee_rate * capture_rate / price_usd) * 365 / mean_supply_near as net_inflation_rate_at_current_volume
from grid
