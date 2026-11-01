{% test in_range(model, column_name, low, high) %}
select {{ column_name }}
from {{ model }}
where {{ column_name }} < {{ low }} or {{ column_name }} > {{ high }}
{% endtest %}
