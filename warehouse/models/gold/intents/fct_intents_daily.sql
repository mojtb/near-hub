-- NEAR Intents per UTC day, one column per source so they can be compared.
-- DefiLlama and revenue.near.org include confidential Intents; NearBlocks counts public Intents only.
with llama_fees as (
    pivot (select date_day, data_type, value_usd from {{ ref('stg_defillama__intents_fees') }} where is_latest)
    on data_type in ('dailyFees', 'dailyRevenue', 'dailyHoldersRevenue', 'dailyProtocolRevenue', 'dailySupplySideRevenue')
    using sum(value_usd)
    group by date_day
),

llama_fee_reads as (
    select date_day, min(snapshot_date) as snapshot_date
    from {{ ref('stg_defillama__intents_fees') }}
    where is_latest
    group by date_day
),

llama_volume as (select date_day, volume_usd from {{ ref('stg_defillama__intents_volume') }} where is_latest),

nb as (
    pivot (select date_day, metric, daily_value from {{ ref('stg_nearblocks__intents_daily') }} where is_latest)
    on metric in ('volume_usd', 'swaps', 'accounts', 'tokens', 'chains')
    using sum(daily_value)
    group by date_day
),

nb_cumulative as (
    select date_day, cumulative_value as cumulative_volume_usd
    from {{ ref('stg_nearblocks__intents_daily') }}
    where is_latest and metric = 'volume_usd'
),

page_volume as (select date_day, volume_usd, cumulative_volume_usd from {{ ref('stg_revenue_page__volume_daily') }} where is_latest),
page_fees as (select date_day, snapshot_date, fees_usd, total_fees_near, cumulative_fees_usd from {{ ref('stg_revenue_page__fees_daily') }} where is_latest),
page_tvl as (select date_day, confidential_tvl_usd from {{ ref('stg_revenue_page__confidential_tvl') }} where is_latest)

select
    d.date_day,
    llama_volume.volume_usd as volume_usd_defillama,
    nb.volume_usd as volume_usd_nearblocks,
    page_volume.volume_usd as volume_usd_revenue_page,
    nb_cumulative.cumulative_volume_usd as cumulative_volume_usd_nearblocks,
    page_volume.cumulative_volume_usd as cumulative_volume_usd_revenue_page,
    cast(nb.swaps as bigint) as swaps_nearblocks,
    cast(nb.accounts as bigint) as accounts_nearblocks,
    cast(nb.tokens as bigint) as tokens_nearblocks,
    cast(nb.chains as bigint) as chains_nearblocks,
    llama_fees.dailyFees as fees_usd_defillama,
    page_fees.fees_usd as fees_usd_revenue_page,
    page_fees.total_fees_near as fees_near_revenue_page,
    llama_fees.dailyRevenue as revenue_usd_defillama,
    llama_fees.dailyHoldersRevenue as holders_revenue_usd_defillama,
    llama_fees.dailyProtocolRevenue as treasury_revenue_usd_defillama,
    llama_fees.dailySupplySideRevenue as supply_side_revenue_usd_defillama,
    page_tvl.confidential_tvl_usd,
    -- Both sources rewrite a day's fees and revenue after first publishing them. Age is counted from each source's
    -- own newest read, not today, so a pinned build gives the same answer and a missed fetch settles nothing.
    coalesce(
        least(page_fees.snapshot_date, llama_fee_reads.snapshot_date) - d.date_day < {{ var('intents_fee_settle_nights') }},
        false
    ) as is_fee_revenue_provisional
from {{ ref('dim_date') }} d
left join llama_volume using (date_day)
left join llama_fees using (date_day)
left join llama_fee_reads using (date_day)
left join nb using (date_day)
left join nb_cumulative using (date_day)
left join page_volume using (date_day)
left join page_fees using (date_day)
left join page_tvl using (date_day)
where llama_volume.date_day is not null or nb.date_day is not null or page_volume.date_day is not null or page_fees.date_day is not null
