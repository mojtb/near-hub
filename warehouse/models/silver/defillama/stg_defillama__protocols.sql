-- Protocols listing NEAR. Point in time: one row per protocol per snapshot.
with files as ({{ bronze_files('defillama__protocols') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as p from files
)

select
    snapshot_date,
    p->>'slug' as protocol_slug,
    p->>'name' as protocol_name,
    p->>'category' as category,
    p->>'url' as url,
    p->>'parentProtocol' as parent_protocol,
    cast(p->'chainTvls'->>'Near' as double) as near_tvl_usd,
    cast(p->>'tvl' as double) as total_tvl_usd,
    {{ is_latest("p->>'slug'") }} as is_latest
from rows
