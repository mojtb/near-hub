-- fct_dev_activity_weekly cuts its weeks on Sunday, as GitHub does, while dim_date.week_start is a Monday, so joining the
-- two on week_start returned nothing. dim_date.week_start_sunday is the column to join on: every week of the weekly
-- table that falls inside the date spine must be found there.
select w.week_start, count(*) as repo_rows
from {{ ref('fct_dev_activity_weekly') }} w
left join (select distinct week_start_sunday from {{ ref('dim_date') }}) d on d.week_start_sunday = w.week_start
where d.week_start_sunday is null
  and w.week_start between (select min(date_day) from {{ ref('dim_date') }}) and (select max(date_day) from {{ ref('dim_date') }})
group by w.week_start
