-- The daily close is an estimate of a transfer-time value. Where FastNear valued a NEAR transfer, the close-price figure
-- stayed within 1.9% of it on the median transfer and within 7.7% on nine in ten (measured 2026-11-05 over 6,091 transfers).
-- A median over 5% would mean the price series and the transfers no longer line up, such as by a day.
with pairs as (
    select abs(t.amount_usd / (t.amount_token * m.price_usd) - 1) as gap
    from {{ ref('fct_wallet_transfers') }} t
    join {{ ref('fct_market_daily') }} m using (date_day)
    where t.asset_id = 'native:near' and t.usd_basis = 'transfer_time' and t.amount_token <> 0 and m.price_usd is not null
)

select count(*) as pairs, quantile_cont(gap, 0.5) as median_gap
from pairs
having count(*) < 1000 or quantile_cont(gap, 0.5) > 0.05
