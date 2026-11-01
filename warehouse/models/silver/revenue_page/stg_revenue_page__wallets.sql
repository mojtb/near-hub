-- Point in time: all-time NEAR received per revenue wallet, as NEAR reports it.
with files as ({{ bronze_files('revenue_page__parsed') }}),

rows as (
    select snapshot_date, {{ explode("doc->'rows'") }} as r from files
)

select
    snapshot_date,
    r->>'name' as account_id,
    cast(r->>'nearAmount' as double) as received_near,
    cast(r->>'share' as double) as share_pct
from rows
