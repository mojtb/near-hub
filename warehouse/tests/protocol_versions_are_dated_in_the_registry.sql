-- A new protocol version can change what the chain's figures mean: version 87 ended the contracts' share of gas, and
-- protocol_upgrades_match_config_reads only watches that one rate, so version 88 arrived on 2026-11-06 without a row.
-- Every version the nightly config reads have shown after the first must therefore be dated to its block in
-- registry/protocol_upgrades.csv, and the date must fit the reads: not after the first read on the new version, and
-- not before the last read on an older one. A read on the day itself can show either, depending on the hour.
with reads as (
    select protocol_version, min(snapshot_date) as first_read, max(snapshot_date) as last_read
    from {{ ref('stg_rpc__protocol_config') }}
    where protocol_version is not null
    group by protocol_version
),

arrived as (
    select
        r.protocol_version,
        r.first_read,
        (select max(o.last_read) from reads o where o.protocol_version < r.protocol_version) as last_read_before
    from reads r
    where r.protocol_version > (select min(protocol_version) from reads)
)

select a.protocol_version, a.last_read_before, a.first_read, cast(u.first_block_utc as date) as registry_day
from arrived a
left join {{ ref('protocol_upgrades') }} u using (protocol_version)
where u.protocol_version is null
   or u.first_block_utc is null
   or cast(u.first_block_utc as date) > a.first_read
   or cast(u.first_block_utc as date) < a.last_read_before
