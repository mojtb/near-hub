{% test min_rows(model, n) %}
select count(*) as row_count
from {{ model }}
having count(*) < {{ n }}
{% endtest %}
