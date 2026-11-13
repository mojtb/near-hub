-- The Bitwise NEAR ETF (NRR) per trading day. Flow is the change in shares times that day's NAV, which is what the flows
-- SoSoValue reports work out to. Bitwise's page shows only the current share count, so history up to the last row of
-- registry/etf_nrr_history.csv comes from that file, where flow_basis says how each row was reached. After that, the
-- change comes from the share counts saved each night. A night without a snapshot leaves that day's flow empty, and the
-- next reading's flow covers the days it missed.
with history as (select * from {{ ref('etf_nrr_history') }}),

readings as (select * from {{ ref('stg_nrr_fund__readings') }} where is_latest),

prices as (select * from {{ ref('stg_nrr_fund__prices') }} where is_latest),

volumes as (
    select premium_as_of as date_day, arg_max(volume_shares, snapshot_date) as volume_shares
    from {{ ref('stg_nrr_fund__readings') }}
    group by 1
),

days as (
    select date_day from history
    union select date_day from readings
    union select date_day from prices
),

joined as (
    select
        d.date_day,
        coalesce(p.nav_usd, h.nav_usd, r.net_assets_usd / r.shares_outstanding) as nav_usd,
        coalesce(p.market_price_usd, h.market_price_usd) as market_price_usd,
        v.volume_shares,
        r.shares_outstanding as fund_page_shares,
        r.net_assets_usd as fund_page_net_assets_usd,
        coalesce(case when r.near_in_trust_as_of = d.date_day then r.near_in_trust end, h.near_in_trust) as near_in_trust,
        r.staked_share,
        r.net_staking_rate,
        r.gross_staking_rate,
        r.listed_wallets,
        h.flow_shares as history_flow_shares,
        h.flow_basis as history_flow_basis,
        h.reported_flow_usd,
        h.reported_cumulative_usd,
        h.reported_net_assets_usd,
        h.source_url,
        h.note,
        d.date_day <= (select max(date_day) from history) as in_history
    from days d
    left join history h using (date_day)
    left join readings r using (date_day)
    left join prices p using (date_day)
    left join volumes v using (date_day)
),

counted as (
    select
        *,
        row_number() over (order by date_day) as day_number,
        case when in_history then sum(history_flow_shares) over (order by date_day) else fund_page_shares end as shares_outstanding
    from joined
),

flows as (
    select
        *,
        near_in_trust / shares_outstanding as known_near_per_share,
        case when in_history then history_flow_shares
             else shares_outstanding - lag(shares_outstanding ignore nulls) over (order by date_day) end as flow_shares,
        case when shares_outstanding is not null
             then day_number - lag(case when shares_outstanding is not null then day_number end ignore nulls) over (order by date_day) end as trading_days_covered
    from counted
),

valued as (
    select
        *,
        coalesce(known_near_per_share, last_value(known_near_per_share ignore nulls) over (order by date_day)) as near_per_share,
        case when coalesce(history_flow_basis, '') <> 'seed_capital' then flow_shares * nav_usd end as flow_usd
    from flows
)

select
    date_day,
    nav_usd,
    market_price_usd,
    100 * (market_price_usd / nav_usd - 1) as premium_discount_pct,
    volume_shares,
    shares_outstanding,
    fund_page_shares,
    coalesce(fund_page_net_assets_usd, shares_outstanding * nav_usd) as net_assets_usd,
    near_in_trust,
    near_per_share,
    flow_shares,
    flow_shares // 10000 as flow_baskets,
    flow_usd,
    flow_shares * near_per_share as flow_near,
    sum(flow_usd) over (order by date_day) as cumulative_flow_usd,
    case when in_history then history_flow_basis when flow_shares is not null then 'fund_page' end as flow_basis,
    trading_days_covered,
    reported_flow_usd,
    reported_cumulative_usd,
    reported_net_assets_usd,
    staked_share,
    net_staking_rate,
    gross_staking_rate,
    listed_wallets,
    source_url,
    note
from valued
