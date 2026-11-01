-- Point in time: headline tiles exactly as the page labels them, such as "$$58.67M" or "634.9K".
with files as ({{ bronze_files('revenue_page__parsed') }}),

rows as (
    select snapshot_date, {{ explode("doc->'stats'") }} as r from files
)

select
    snapshot_date,
    r->>'label' as label,
    replace(r->>'value', '$$', '$') as display_value,
    r->>'sub' as description
from rows
