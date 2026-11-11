-- Market cap over a year of income, for NEAR and its peers, on five different ideas of income. The choice of basis
-- changes NEAR's rank more than anything else, so each basis is its own row and none is the default:
--   gas_fees        what users paid the chain itself in transaction fees
--   app_fees        what users paid the applications on the chain
--   all_fees        the two together
--   app_revenue     the part of app fees the applications or their tokens keep; it does not go to the chain's own token
--   holder_revenue  NEAR only: gas burned plus NEAR received by the three revenue wallets, which is held, not burned
-- A year of income is the trailing 30 days times 365/30. Market caps are not on one definition across chains: see
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

-- By calendar days, not rows, because two peers have old holes in their series; a window with a hole gets no multiple.
windows as (
    select
        date_day,
        chain_id,
        basis,
        sum(value_usd) over w as basis_30d_usd,
        count(value_usd) over w as days_with_value
    from income
    window w as (partition by chain_id, basis order by date_day range between interval 29 days preceding and current row)
)

select
    w.date_day,
    w.chain_id,
    w.basis,
    w.basis_30d_usd,
    p.market_cap_usd / (w.basis_30d_usd * 365 / 30) as multiple,
    p.is_fee_revenue_provisional as is_provisional
from windows w
join peer p using (date_day, chain_id)
where w.days_with_value = 30 and w.basis_30d_usd > 0 and p.market_cap_usd is not null
