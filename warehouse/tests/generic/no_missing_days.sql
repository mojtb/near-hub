{# A daily series should hold every day between its first and its last. `allowed` is the number of missing days a series
   may have, for a source with known old holes; `partition_by` checks each series of a table on its own. #}
{% test no_missing_days(model, day_column, partition_by=none, allowed=0) %}
with days as (
    select distinct {% if partition_by %}cast({{ partition_by }} as varchar){% else %}'all'{% endif %} as series, {{ day_column }} as day
    from {{ model }}
    where {{ day_column }} is not null
),

steps as (
    select series, day, lead(day) over (partition by series order by day) as next_day from days
)

select series, sum(next_day - day - 1) as missing_days, min(day) as first_gap_after, max(day) as last_gap_after
from steps
where next_day - day > 1
group by series
having sum(next_day - day - 1) > {{ allowed }}
{% endtest %}
