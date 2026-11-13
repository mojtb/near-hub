-- Every priced asset in registry/token_prices.csv must have a series that starts on its first_price_day and reaches the
-- newest days of the table, and an asset the registry gives no source must have no rows. With no_missing_days on the
-- table, that is one price for each asset on every day from its first day on. A source that drops an asset, renames its
-- id or loses its early history would otherwise leave balances without a value and nothing would say so.
with newest as (select max(date_day) as newest_day from {{ ref('fct_token_price_daily') }}),

series as (
    select symbol, min(date_day) as first_day, max(date_day) as last_day
    from {{ ref('fct_token_price_daily') }}
    group by symbol
)

select t.symbol, t.price_source, t.first_price_day, s.first_day, s.last_day, newest.newest_day
from {{ ref('token_prices') }} t
cross join newest
left join series s using (symbol)
where (t.price_source is not null
        and (s.first_day is null or s.first_day <> t.first_price_day or newest.newest_day - s.last_day > 3))
    or (t.price_source is null and s.symbol is not null)
