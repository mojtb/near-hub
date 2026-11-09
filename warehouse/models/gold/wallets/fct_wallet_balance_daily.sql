-- Native NEAR balance per crawled wallet per day: the last running balance FastNear reports that day,
-- carried forward over days without transfers. dq_reconciliation compares it with NearBlocks' own balance series.
with last_of_day as (
    select
        account_id,
        date_day,
        arg_max({{ yocto_to_near('end_of_block_balance_raw') }}, block_height) as balance_near
    from {{ ref('stg_fastnear__transfers') }}
    where asset_id = 'native:near' and end_of_block_balance_raw is not null
    group by all
),

bounds as (
    select account_id, min(date_day) as first_day from last_of_day group by account_id
),

as_of_day as (
    select max(date_day) as last_day from {{ ref('dim_date') }}
),

spine as (
    select b.account_id, d.date_day
    from bounds b
    cross join as_of_day a
    join {{ ref('dim_date') }} d on d.date_day between b.first_day and a.last_day
),

filled as (
    select
        s.account_id,
        s.date_day,
        last_value(l.balance_near ignore nulls) over (
            partition by s.account_id order by s.date_day rows between unbounded preceding and current row
        ) as balance_near,
        l.balance_near is not null as has_transfer_on_day
    from spine s
    left join last_of_day l using (account_id, date_day)
)

select date_day, account_id, balance_near, has_transfer_on_day
from filled
