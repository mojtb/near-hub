-- Protocols DefiLlama lists on NEAR, with TVL as of the newest reading. is_cex marks exchange wallets.
select
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
