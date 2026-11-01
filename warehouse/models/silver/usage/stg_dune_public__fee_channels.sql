-- All-time gross fees per referral channel, read from the public dashboard's table.
with files as ({{ bronze_files('dune_public__near_intents_dashboard') }}),

rows as (
    select snapshot_date, {{ explode("doc->'fee_channels'") }} as c from files
)

select
    snapshot_date,
    c->>'referral' as referral,
    cast(c->>'fees_usd' as double) as fees_usd
from rows
