select event_date, event_type, title, detail, source_url, status
from {{ ref('events') }}
