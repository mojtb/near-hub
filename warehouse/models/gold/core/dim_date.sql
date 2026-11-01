with bounds as (
    select min(date_day) as first_day, max(date_day) as last_day
    from (
        select date_day from {{ ref('stg_nearblocks__charts_v1') }}
        union all
        select date_day from {{ ref('stg_defillama__intents_volume') }}
    )
),

days as (
    select cast(unnest(generate_series(first_day, last_day, interval 1 day)) as date) as date_day
    from bounds
)

select
    date_day,
    cast(date_trunc('week', date_day) as date) as week_start,
    cast(date_trunc('month', date_day) as date) as month_start,
    cast(date_trunc('quarter', date_day) as date) as quarter_start,
    year(date_day) as calendar_year,
    date_day >= date '2026-02-23' as is_fee_switch_active
from days
