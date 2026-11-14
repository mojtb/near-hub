-- The pool's wNEAR is read at the end of every complete month, from the contract's first to the one before the newest
-- day read. A month left out would let a quarter's mean rest on two readings without saying so.
with month_ends as (
    select date_day
    from {{ ref('fct_intents_pool_chain_monthly') }}
    where is_month_end and token_class = 'native_wrapped'
),

span as (
    select
        (select min(date_day) from month_ends) as first_end,
        max(case when is_month_end then date_day else cast(date_trunc('month', date_day) as date) - 1 end) as last_end
    from {{ ref('fct_intents_pool_chain_monthly') }}
),

expected as (
    select last_day(cast(unnest(generate_series(date_trunc('month', first_end), date_trunc('month', last_end), interval 1 month)) as date)) as date_day
    from span
)

select date_day as missing_month_end
from expected
where date_day not in (select date_day from month_ends)
