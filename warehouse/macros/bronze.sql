{# Use exactly the schema named in dbt_project.yml: silver, gold, registry. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name or target.schema }}
{%- endmacro %}


{# One row per bronze file: its snapshot date, its key, and the whole document as JSON.
   Snapshots after var('as_of') are invisible, which is what makes a pinned build stable. #}
{% macro bronze_files(table) %}
    {%- set relation = source('bronze', table) -%}
    {%- set has_files = true -%}
    {%- if execute -%}
        {%- set pattern = 'data/bronze/' ~ table | replace('__', '/') ~ '/dt=*/*.json.gz' -%}
        {%- set found = run_query("select count(*) from glob('" ~ pattern ~ "')").columns[0].values()[0] -%}
        {%- set has_files = found > 0 -%}
    {%- endif -%}
    {%- if has_files %}
    select
        cast(regexp_extract(filename, 'dt=(\d{4}-\d{2}-\d{2})', 1) as date) as snapshot_date,
        regexp_extract(filename, '/([^/]+)\.json\.gz$', 1) as file_key,
        json as doc
    from {{ relation }}
    where cast(regexp_extract(filename, 'dt=(\d{4}-\d{2}-\d{2})', 1) as date) <= cast('{{ var("as_of") }}' as date)
    {%- else %}
    {# A keyed source that has not run yet: an empty, correctly typed result, so the build still works. #}
    select cast(null as date) as snapshot_date, cast(null as varchar) as file_key, cast(null as json) as doc where false
    {%- endif %}
{% endmacro %}


{# Each element of a JSON array, as JSON. Values are read with ->> as text, so yocto amounts keep every digit. #}
{% macro explode(json_expr) -%}
    unnest(from_json({{ json_expr }}, '["JSON"]'))
{%- endmacro %}


{# True on the newest snapshot's row for a key. Silver keeps every snapshot, so restated values stay visible.
   Pages within one snapshot can overlap, so `tiebreak` must be given where a key can repeat: without it the
   winning row would vary between builds. #}
{% macro is_latest(key_columns, tiebreak=none) -%}
    row_number() over (partition by {{ key_columns }} order by snapshot_date desc{% if tiebreak %}, {{ tiebreak }} desc nulls last{% endif %}) = 1
{%- endmacro %}


{# yoctoNEAR text to NEAR, exact to six decimals: 1 NEAR = 10^24 yoctoNEAR, and integer division keeps every digit until then. #}
{% macro yocto_to_near(text_expr) -%}
    (cast(split_part({{ text_expr }}, '.', 1) as hugeint) // 1000000000000000000) / 1000000.0
{%- endmacro %}


{# Unix seconds to a UTC date. make_timestamp is naive, so neither the machine's time zone nor an extension can change the result. #}
{% macro unix_day(expr) -%}
    cast(make_timestamp(cast({{ expr }} as bigint) * 1000000) as date)
{%- endmacro %}
