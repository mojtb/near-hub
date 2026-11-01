-- Fees and revenue per protocol on NEAR, as of each DefiLlama reading.
select
    snapshot_date,
    case data_type when 'dailyRevenue' then 'revenue' else 'fees' end as measure,
    protocol_name,
    protocol_slug,
    category,
    total_24h_usd,
    total_7d_usd,
    total_30d_usd,
    total_1y_usd,
    total_all_time_usd
from {{ ref('stg_defillama__chain_fee_protocols') }}
where llama_chain = 'Near'
