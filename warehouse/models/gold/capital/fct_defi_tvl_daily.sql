-- DefiLlama's TVL for the NEAR chain per day, made usable for a chart over time: the same figure counted in NEAR, and
-- a flag for the days on which DefiLlama's reading of the largest protocol in it halved and later came back.
-- The figure is fct_peer_daily.tvl_usd for NEAR. It counts lending, DEXs and restaking, and leaves out liquid
-- staking, bridges, tokenised assets and exchange wallets. Each day's value is the state as that day began, so it is
-- divided by NEAR's close on the day before.
-- A day is a fault when Rhea Lend's TVL counted in NEAR is under 75% of its median over the 61 days centred on that
-- day, once the protocol has 30 days of history. It is counted in NEAR so that a move in NEAR's price is not taken for
-- a fault, and Rhea Lend is read because it is most of the figure and the readings that halve are its own: the
-- staking tokens in it and NEAR's price do not move on those days. At the newest day the window holds earlier days
-- only, so a fault is caught on the day it is read. The rule cannot tell a fault from a real fall that reverses
-- within a month; the sixteen days of September 2025 are read as a fault.
with price as (
    select date_day, price_usd from {{ ref('fct_market_daily') }}
),

chain as (
    select c.date_day, c.tvl_usd, p.price_usd as near_price_day_before_usd, c.tvl_usd / p.price_usd as tvl_in_near
    from {{ ref('fct_peer_daily') }} c
    left join price p on p.date_day = c.date_day - 1
    where c.chain_id = 'near' and c.tvl_usd is not null
),

-- One DefiLlama id, so a rename of the protocol keeps the series
rhea_lend as (
    select
        t.date_day,
        t.tvl_usd as rhea_lend_tvl_usd,
        t.tvl_usd / p.price_usd as rhea_lend_tvl_in_near,
        count(*) over (order by t.date_day range between interval 30 day preceding and interval 1 day preceding) as days_before
    from {{ ref('fct_protocol_tvl_daily') }} t
    join price p on p.date_day = t.date_day - 1
    where t.protocol_id = '1546'
),

judged as (
    select
        *,
        median(rhea_lend_tvl_in_near) over (
            order by date_day range between interval 30 day preceding and interval 30 day following
        ) as rhea_lend_usual_in_near
    from rhea_lend
)

select
    c.date_day,
    c.tvl_usd,
    c.near_price_day_before_usd,
    c.tvl_in_near,
    j.rhea_lend_tvl_usd,
    j.rhea_lend_tvl_in_near,
    j.rhea_lend_usual_in_near,
    coalesce(j.days_before >= 30 and j.rhea_lend_tvl_in_near < 0.75 * j.rhea_lend_usual_in_near, false) as is_fault
from chain c
left join judged j using (date_day)
