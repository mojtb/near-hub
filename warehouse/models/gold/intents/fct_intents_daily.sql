-- NEAR Intents per UTC day, one column per measure.
-- All-route volume and gross fees come from revenue.near.org, which counts confidential routes too. On days the page does
-- not have, DefiLlama fills in: 22 days of December 2024 and 7 days between 2025-03-08 and 05-14 for volume, 5 days of May
-- 2025 for fees. volume_basis and fees_basis say which source a day's figure is from. DefiLlama's own series cannot stand
-- alone, because its scope changes during 2026: it counts public routes only from 2026-04-01 (volume to 08-31, fees to
-- 09-13), so dq_reconciliation compares it with the page and NearBlocks instead (docs/REDUNDANCY_AUDIT_2026-11-09.md).
-- Public volume, swaps, accounts, tokens and chains come from NearBlocks, which sees public Intents only. Captured revenue
-- is DefiLlama's, which is the revenue wallets' NEAR at the day's close; fct_revenue_inflows_daily rebuilds it from transfers.
with llama_volume as (select date_day, volume_usd from {{ ref('stg_defillama__intents_volume') }} where is_latest),

llama_fees as (
    select
        date_day,
        sum(value_usd) filter (where data_type = 'dailyFees') as fees_usd,
        sum(value_usd) filter (where data_type = 'dailyRevenue') as revenue_usd,
        min(snapshot_date) as snapshot_date
    from {{ ref('stg_defillama__intents_fees') }}
    where is_latest and data_type in ('dailyFees', 'dailyRevenue')
    group by date_day
),

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

page_volume as (select date_day, volume_usd from {{ ref('stg_revenue_page__volume_daily') }} where is_latest),
page_fees as (select date_day, snapshot_date, fees_usd from {{ ref('stg_revenue_page__fees_daily') }} where is_latest),
page_tvl as (select date_day, confidential_tvl_usd from {{ ref('stg_revenue_page__confidential_tvl') }} where is_latest)

select
    d.date_day,
    coalesce(page_volume.volume_usd, llama_volume.volume_usd) as volume_usd,
    case
        when page_volume.volume_usd is not null then 'revenue_page'
        when llama_volume.volume_usd is not null then 'defillama'
    end as volume_basis,
    nb.volume_usd as public_volume_usd,
    nb_cumulative.cumulative_volume_usd as public_volume_cumulative_usd,
    cast(nb.swaps as bigint) as public_swaps,
    cast(nb.accounts as bigint) as public_accounts,
    cast(nb.tokens as bigint) as public_tokens,
    cast(nb.chains as bigint) as public_chains,
    coalesce(page_fees.fees_usd, llama_fees.fees_usd) as fees_usd,
    case
        when page_fees.fees_usd is not null then 'revenue_page'
        when llama_fees.fees_usd is not null then 'defillama'
    end as fees_basis,
    llama_fees.revenue_usd,
    page_tvl.confidential_tvl_usd,
    -- Both sources rewrite a day's fees and revenue after first publishing them. Age is counted from each source's
    -- own newest read, not today, so a pinned build gives the same answer and a missed fetch settles nothing.
    coalesce(
        least(page_fees.snapshot_date, llama_fees.snapshot_date) - d.date_day < {{ var('intents_fee_settle_nights') }},
        false
    ) as is_fee_revenue_provisional
from {{ ref('dim_date') }} d
left join llama_volume using (date_day)
left join llama_fees using (date_day)
left join nb using (date_day)
left join nb_cumulative using (date_day)
left join page_volume using (date_day)
left join page_fees using (date_day)
left join page_tvl using (date_day)
where llama_volume.date_day is not null or nb.date_day is not null or page_volume.date_day is not null or page_fees.date_day is not null
