-- Protocols DefiLlama lists on NEAR, with TVL as of the newest reading that listed each one. is_cex marks exchange wallets.
-- One row per DefiLlama id, under its newest slug. An older read_on means the protocol was missing from later readings.
select
    protocol_id,
    protocol_slug,
    protocol_name,
    category,
    url,
    parent_protocol,
    near_tvl_usd,
    total_tvl_usd,
    category = 'CEX' as is_cex,
    snapshot_date as read_on
from {{ ref('stg_defillama__protocols') }}
where is_latest
