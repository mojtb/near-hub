-- Fees and revenue per application on each of the seven chains, as of each DefiLlama reading, with DefiLlama's
-- category for the application. These are the rows behind fct_peer_daily.fees_usd and revenue_usd. The chain's own
-- row (category Chain: its transaction fees) is not here; it is fct_peer_chain_fees_snapshot.
-- A reading's 30 days are DefiLlama's trailing 30 days at the moment of the read, not a calendar window, so they
-- differ a little from 30 days summed in fct_peer_daily. The readings begin on 2026-11-01 for all seven chains;
-- NEAR alone has one of 2026-10-28, with fees only.
with listed as (
    select s.snapshot_date, p.chain_id, s.protocol_name, s.protocol_slug, s.category, s.data_type,
        s.total_24h_usd, s.total_7d_usd, s.total_30d_usd, s.total_1y_usd
    from {{ ref('stg_defillama__chain_fee_protocols') }} s
    join {{ ref('peers') }} p using (llama_chain)
    where coalesce(s.category, '') <> 'Chain'
),

apps as (
    select
        snapshot_date,
        chain_id,
        protocol_name,
        max(protocol_slug) as protocol_slug,
        max(category) as category,
        max(total_24h_usd) filter (where data_type = 'dailyFees') as fees_24h_usd,
        max(total_7d_usd) filter (where data_type = 'dailyFees') as fees_7d_usd,
        max(total_30d_usd) filter (where data_type = 'dailyFees') as fees_30d_usd,
        max(total_1y_usd) filter (where data_type = 'dailyFees') as fees_1y_usd,
        max(total_24h_usd) filter (where data_type = 'dailyRevenue') as revenue_24h_usd,
        max(total_7d_usd) filter (where data_type = 'dailyRevenue') as revenue_7d_usd,
        max(total_30d_usd) filter (where data_type = 'dailyRevenue') as revenue_30d_usd,
        max(total_1y_usd) filter (where data_type = 'dailyRevenue') as revenue_1y_usd
    from listed
    group by 1, 2, 3
)

select
    a.snapshot_date,
    a.chain_id,
    a.protocol_name,
    a.protocol_slug,
    a.category,
    a.fees_24h_usd,
    a.fees_7d_usd,
    a.fees_30d_usd,
    a.fees_1y_usd,
    a.revenue_24h_usd,
    a.revenue_7d_usd,
    a.revenue_30d_usd,
    a.revenue_1y_usd,
    a.fees_30d_usd / nullif(sum(a.fees_30d_usd) over (partition by a.snapshot_date, a.chain_id), 0) as share_of_chain_fees_30d,
    a.snapshot_date = max(a.snapshot_date) over () as is_newest_reading
from apps a
