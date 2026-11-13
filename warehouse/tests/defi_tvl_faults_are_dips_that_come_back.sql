-- fct_defi_tvl_daily marks the days on which DefiLlama's reading of Rhea Lend halved and came back. The flag has to
-- stay a mark for rare dips: two days known to be faults are flagged (2026-04-19, when the reading fell by three
-- quarters for a day, and 2025-11-09), no day in Rhea Lend's first 30 is judged, no calendar year has more than a
-- fifth of its days flagged (2025 and 2026 each have about 6%, and one more episode like September 2025's sixteen days
-- must not turn a nightly red), and a flagged day reads below the clean days of its own month.
with days as (
    select * from {{ ref('fct_defi_tvl_daily') }}
),

known as (
    select d.date_day, 'a known fault day is not flagged' as problem
    from days d
    where d.date_day in (date '2025-11-09', date '2026-04-19') and not d.is_fault
),

early as (
    select d.date_day, 'a day in the first 30 of Rhea Lend is flagged' as problem
    from days d
    where d.is_fault
      and d.date_day < (select min(date_day) from days where rhea_lend_tvl_usd is not null) + 30
),

too_many as (
    select min(date_day) as date_day, 'over a fifth of a year is flagged' as problem
    from days
    group by year(date_day)
    having count(*) filter (where is_fault) > 0.2 * count(*)
),

not_a_dip as (
    select f.date_day, 'a flagged day is not below the clean days of its month' as problem
    from days f
    join (
        select date_trunc('month', date_day) as month_start, median(tvl_in_near) as clean_in_near
        from days where not is_fault group by 1
    ) m on m.month_start = date_trunc('month', f.date_day)
    where f.is_fault and f.tvl_in_near >= m.clean_in_near
)

select * from known
union all
select * from early
union all
select * from too_many
union all
select * from not_a_dip
