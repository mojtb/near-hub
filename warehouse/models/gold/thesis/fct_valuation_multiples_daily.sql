-- Market cap over a year of income, for NEAR and its peers, on five different ideas of income. The choice of basis
-- changes NEAR's rank more than anything else, so each basis is its own row and none is the default:
--   gas_fees        what users paid the chain itself in transaction fees
--   app_fees        what users paid the applications on the chain
--   all_fees        the two together
--   app_revenue     the part of app fees the applications or their tokens keep; it does not go to the chain's own token
--   holder_revenue  NEAR only: gas burned plus NEAR received by the three revenue wallets, which is held, not burned
-- A year of income is the trailing 30 days times 365/30. The same multiple is also given on the trailing 90 days
-- (times 365/90) and on the trailing 365 days as they are. Market caps are not on one definition across chains: see
-- fct_peer_daily.market_cap_basis.
with peer as (select * from {{ ref('fct_peer_daily') }}),

near_holder as (
    select s.date_day, s.burn_near * m.price_usd + coalesce(i.received_usd, 0) as value_usd
    from {{ ref('fct_supply_daily') }} s
    join {{ ref('fct_market_daily') }} m using (date_day)
    left join (select date_day, sum(received_usd) as received_usd from {{ ref('fct_revenue_inflows_daily') }} group by 1) i using (date_day)
),

income as (
    select date_day, chain_id, 'gas_fees' as basis, gas_fees_usd as value_usd from peer
    union all select date_day, chain_id, 'app_fees', fees_usd from peer
    union all select date_day, chain_id, 'all_fees', fees_usd + gas_fees_usd from peer
    union all select date_day, chain_id, 'app_revenue', revenue_usd from peer
    union all select date_day, 'near', 'holder_revenue', value_usd from near_holder
),

-- By calendar days, not rows, because two peers have holes in their series. A window may lack one day in thirty:
-- its sum is then scaled up to the whole window, and days_with_value says so. A window that lacks more gets no
-- figure. Without this, one empty day in Sui's gas series removed Sui from two bases for the next 30 days.
windows as (
    select
        date_day,
        chain_id,
        basis,
        sum(value_usd) over w30 as sum_30d_usd,
        count(value_usd) over w30 as days_with_value,
        sum(value_usd) over w90 as sum_90d_usd,
        count(value_usd) over w90 as days_with_value_90d,
        sum(value_usd) over w365 as sum_365d_usd,
        count(value_usd) over w365 as days_with_value_365d,
        min(date_day) filter (where value_usd is not null) over (partition by chain_id, basis) as first_day
    from income
    window
        w30 as (partition by chain_id, basis order by date_day range between interval 29 days preceding and current row),
        w90 as (partition by chain_id, basis order by date_day range between interval 89 days preceding and current row),
        w365 as (partition by chain_id, basis order by date_day range between interval 364 days preceding and current row)
),

-- A full window keeps its sum as it is, so nothing moves on the days that had a figure before. A window that
-- reaches back before the series began is not a window with a hole, and gets no figure.
scaled as (
    select
        date_day,
        chain_id,
        basis,
        days_with_value,
        days_with_value_90d,
        days_with_value_365d,
        case when date_day < first_day + 29 then null
             when days_with_value = 30 then sum_30d_usd
             when days_with_value = 29 then sum_30d_usd * 30 / 29 end as basis_30d_usd,
        case when date_day < first_day + 89 then null
             when days_with_value_90d = 90 then sum_90d_usd
             when days_with_value_90d >= 87 then sum_90d_usd * 90 / days_with_value_90d end as basis_90d_usd,
        case when date_day < first_day + 364 then null
             when days_with_value_365d = 365 then sum_365d_usd
             when days_with_value_365d >= 353 then sum_365d_usd * 365 / days_with_value_365d end as basis_365d_usd
    from windows
)

select
    w.date_day,
    w.chain_id,
    w.basis,
    w.basis_30d_usd,
    p.market_cap_usd / (w.basis_30d_usd * 365 / 30) as multiple,
    p.is_fee_revenue_provisional as is_provisional,
    w.days_with_value,
    w.basis_90d_usd,
    p.market_cap_usd / nullif(w.basis_90d_usd * 365 / 90, 0) as multiple_90d,
    w.days_with_value_90d,
    w.basis_365d_usd,
    p.market_cap_usd / nullif(w.basis_365d_usd, 0) as multiple_365d,
    w.days_with_value_365d
from scaled w
join peer p using (date_day, chain_id)
where w.basis_30d_usd > 0 and p.market_cap_usd is not null
