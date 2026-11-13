-- What the NEAR Intents contract held of named tokens at each month end, read from the chain itself and not from NEAR's
-- dashboard: wNEAR, the dollar tokens and the tokens of the pool's other main assets that registry/token_prices.csv
-- lists with a price, at the first block of the next
-- UTC day, for every complete month since the contract was deployed in November 2024, and for the newest day read.
-- intents.near holds public and confidential balances alike, so each balance is the whole pool's balance of that token.
-- This is a list of named tokens and not the whole pool: do not add the rows up into one. A token has no row before
-- its contract existed. Every balance is in token units. A dollar token is valued at one dollar each, wNEAR at NEAR's
-- price for the day (fct_market_daily) and another asset at its price in fct_token_price_daily, joined on
-- dashboard_symbol and date_day; an asset with no price that day keeps an empty value. No price comes from NEAR's
-- dashboard. dq_reconciliation holds these readings against the dashboard's series, which is what the site charts.
with reads as (
    select *
    from {{ ref('stg_rpc__intents_pool_history') }}
    where is_latest and error is null
),

newest as (select max(date_day) as d from reads),

dashboard as (select distinct symbol from {{ ref('fct_dune_intents_tvl_asset_daily') }})

select
    r.date_day,
    r.date_day = last_day(r.date_day) as is_month_end,
    r.asset_id,
    r.contract_id,
    r.symbol,
    d.symbol as dashboard_symbol,
    case r.chosen_as when 'wrapped_near' then 'native_wrapped' when 'dollar_token' then 'stablecoin' else 'other' end as token_class,
    r.amount_token,
    case r.chosen_as
        when 'dollar_token' then r.amount_token
        when 'wrapped_near' then r.amount_token * n.price_usd
        else r.amount_token * p.price_usd
    end as value_usd,
    case
        when r.chosen_as = 'dollar_token' then 'one_dollar'
        when r.chosen_as = 'wrapped_near' and n.price_usd is not null then 'near_price'
        when r.chosen_as <> 'wrapped_near' and p.price_usd is not null then 'token_price'
        else 'no_price'
    end as value_status,
    r.block_height,
    r.snapshot_date
from reads r
cross join newest
left join dashboard d on d.symbol = r.symbol
left join {{ ref('fct_market_daily') }} n on n.date_day = r.date_day
left join {{ ref('fct_token_price_daily') }} p on p.symbol = d.symbol and p.date_day = r.date_day
where (r.date_day = last_day(r.date_day) or r.date_day = newest.d)
  and (r.chosen_as in ('wrapped_near', 'dollar_token') or d.symbol in (select symbol from {{ ref('token_prices') }}))
