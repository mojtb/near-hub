-- NEAR's circulating supply per UTC day, built from the chain. NEAR defines it as every token not subject to a lockup at that
-- moment, and NEAR Explorer computed it as total supply, minus what each lockup contract still locks, minus the balances of
-- lockup.near and contributors.near. This follows Explorer, at the close of each day. It starts on 2020-10-13, when transfers
-- were enabled: before that no token could move. See docs/CIRCULATING_SUPPLY.md for the method and its tests.
-- Total supply is read from fct_supply_daily, which holds it, and is not repeated here.
with schedules as (
    select *, {{ lockup_dates() }}
    from {{ ref('stg_rpc__lockups') }}
    where is_latest and lockup_amount_near is not null
),

days as (
    select
        date_day,
        total_supply_near,
        -- The first moment of the next day, in nanoseconds since 1970, which closes this one.
        (date_diff('day', date '1970-01-01', date_day) + 1) * 86400e9 as close_ns
    from {{ ref('fct_supply_daily') }}
    where date_day >= date '2020-10-13' and total_supply_near is not null
),

locked as (
    select
        d.date_day,
        sum({{ lockup_locked_near('d.close_ns') }}) as lockup_locked_near,
        count(*) filter (where {{ lockup_locked_near('d.close_ns') }} > 0) as lockups_still_locking,
        count(*) filter (where d.close_ns >= created_ns and d.close_ns < coalesce(gone_ns, 1e30)) as lockups_existing,
        sum(lockup_amount_near - case when d.close_ns >= coalesce(finished_ns, 1e30) then last_withdrawn_near else first_withdrawn_near end)
            filter (where status = 'live' and transfers_enabled = false and d.close_ns >= created_ns) as transfers_never_enabled_near
    from days d, schedules
    group by d.date_day
),

balances as (
    select account_id, date_day, balance_near
    from {{ ref('stg_rpc__lockup_foundation_balances') }}
    where is_latest and read_with = 'transfers'
),

foundation as (
    select d.date_day, sum(b.balance_near) as foundation_locked_near
    from days d
    cross join (select distinct account_id from balances) a
    asof left join balances b on a.account_id = b.account_id and d.date_day >= b.date_day
    group by d.date_day
)

select
    d.date_day,
    l.lockup_locked_near,
    f.foundation_locked_near,
    d.total_supply_near - l.lockup_locked_near - f.foundation_locked_near as circulating_supply_near,
    (d.total_supply_near - l.lockup_locked_near - f.foundation_locked_near) / d.total_supply_near as circulating_share_of_total,
    l.lockups_existing,
    l.lockups_still_locking,
    coalesce(l.transfers_never_enabled_near, 0) as transfers_never_enabled_near
from days d
join locked l using (date_day)
join foundation f using (date_day)
