{# The first day of the unbroken run of tallied 1Click days: the day after the newest missing day, or the first day when
   none is missing. Each 1Click table compares its own date_day with it, so all six flag the same days and none has to
   read another: a breakdown table that took the flag from fct_intents_1click_daily would also inherit that table's
   lineage to fct_intents_daily, and look as if it read DefiLlama, NearBlocks and revenue.near.org. #}
{% macro oneclick_daily_run_start() -%}
(
    select coalesce(max(date_day) filter (where date_day - previous_day > 1), min(date_day))
    from (
        select date_day, lag(date_day) over (order by date_day) as previous_day
        from {{ ref('stg_intents_explorer__days') }}
        where is_latest
    )
)
{%- endmacro %}
