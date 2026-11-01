-- Dated readings of the public NEAR Intents dashboard page. NEAR uploads the data behind this dashboard.
with files as ({{ bronze_files('dune_public__near_intents_dashboard') }}),

rows as (
    select snapshot_date, {{ explode("doc->'tiles'") }} as t from files
)

select
    snapshot_date,
    t->>'scope' as scope,
    t->>'metric' as metric,
    cast(t->>'value_usd' as double) as value_usd
from rows
