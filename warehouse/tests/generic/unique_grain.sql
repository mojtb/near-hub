{% test unique_grain(model, columns) %}
select {{ columns | join(', ') }}, count(*) as duplicates
from {{ model }}
group by all
having count(*) > 1
{% endtest %}
