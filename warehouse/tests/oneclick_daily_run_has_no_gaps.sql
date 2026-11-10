-- is_in_daily_run promises that a sum over its rows misses no day: the flagged days of fct_intents_1click_daily must be
-- consecutive and end on the table's newest day, and the five breakdown tables must flag the same days.
with daily as (
    select
        count(*) filter (where is_in_daily_run) as flagged_days,
        min(date_day) filter (where is_in_daily_run) as first_day,
        max(date_day) filter (where is_in_daily_run) as last_day,
        max(date_day) as newest_day
    from {{ ref('fct_intents_1click_daily') }}
),

breakdowns as (
    select 'fct_intents_1click_channel_daily' as table_name, date_day, is_in_daily_run from {{ ref('fct_intents_1click_channel_daily') }}
    union all select 'fct_intents_1click_pair_daily', date_day, is_in_daily_run from {{ ref('fct_intents_1click_pair_daily') }}
    union all select 'fct_intents_1click_route_daily', date_day, is_in_daily_run from {{ ref('fct_intents_1click_route_daily') }}
    union all select 'fct_intents_1click_size_daily', date_day, is_in_daily_run from {{ ref('fct_intents_1click_size_daily') }}
    union all select 'fct_intents_1click_fee_recipient_daily', date_day, is_in_daily_run from {{ ref('fct_intents_1click_fee_recipient_daily') }}
)

select 'fct_intents_1click_daily' as table_name, first_day as date_day, 'the flagged days have a gap or stop before the newest day' as problem
from daily
where newest_day is not null
  and (flagged_days is distinct from last_day - first_day + 1 or last_day is distinct from newest_day)

union all

select b.table_name, b.date_day, 'the flag differs from fct_intents_1click_daily'
from breakdowns b
left join {{ ref('fct_intents_1click_daily') }} d using (date_day)
where b.is_in_daily_run is distinct from coalesce(d.is_in_daily_run, false)
