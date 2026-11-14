-- How concentrated NEAR Intents is, per month, along four cuts: 1Click channels by volume and by fees, and all-route
-- volume by blockchain and by asset. One row per month and cut, with the Herfindahl index and the largest members'
-- shares. The blockchain and asset cuts read NEAR's dashboard on Dune, which splits every route, confidential ones
-- included; NearBlocks' public split covered under a fifth of volume once settlement went confidential on 2026-11-03.
-- The dashboard is read on request, so these two cuts stop at its last reading. covered_share_of_volume says how
-- much of all-route volume a cut can see.
with channel_rows as (
    select * from {{ ref('fct_intents_1click_channel_daily') }} where is_in_daily_run and status = 'SUCCESS'
),

members as (
    select cast(date_trunc('month', date_day) as date) as month_start, 'channel_volume' as dimension, referral as member,
        sum(amount_in_usd) as value_usd, count(distinct date_day) as member_days
    from channel_rows group by 1, 3
    union all
    select cast(date_trunc('month', date_day) as date), 'channel_fees', referral, sum(app_fee_usd), count(distinct date_day)
    from channel_rows group by 1, 3
    union all
    select cast(date_trunc('month', date_day) as date), 'chain_volume', blockchain, sum(volume_usd), count(distinct date_day)
    from {{ ref('fct_dune_intents_chain_daily') }} group by 1, 3
    union all
    select cast(date_trunc('month', date_day) as date), 'asset_volume', symbol, sum(volume_usd), count(distinct date_day)
    from {{ ref('fct_dune_intents_asset_daily') }} group by 1, 3
),

days_seen as (
    select cast(date_trunc('month', date_day) as date) as month_start, 'channel_volume' as dimension, count(distinct date_day) as days_counted from channel_rows group by 1
    union all select cast(date_trunc('month', date_day) as date), 'channel_fees', count(distinct date_day) from channel_rows group by 1
    union all select cast(date_trunc('month', date_day) as date), 'chain_volume', count(distinct date_day) from {{ ref('fct_dune_intents_chain_daily') }} group by 1
    union all select cast(date_trunc('month', date_day) as date), 'asset_volume', count(distinct date_day) from {{ ref('fct_dune_intents_asset_daily') }} group by 1
),

shares as (
    select
        month_start,
        dimension,
        member,
        value_usd,
        value_usd / sum(value_usd) over (partition by month_start, dimension) as member_share,
        row_number() over (partition by month_start, dimension order by value_usd desc, member) as member_rank
    from members
    where value_usd > 0
),

all_routes as (
    select cast(date_trunc('month', date_day) as date) as month_start, sum(volume_usd) as volume_usd
    from {{ ref('fct_intents_daily') }}
    group by 1
)

select
    s.month_start,
    s.dimension,
    d.days_counted = day(last_day(s.month_start)) as is_month_complete,
    count(*) as members,
    sum(s.value_usd) as total_usd,
    sum(s.member_share * s.member_share) as hhi,
    max(s.member_share) as top_1_share,
    sum(s.member_share) filter (where s.member_rank <= 3) as top_3_share,
    sum(s.member_share) filter (where s.member_rank <= 10) as top_10_share,
    max(s.member) filter (where s.member_rank = 1) as top_member,
    case when s.dimension <> 'channel_fees' then sum(s.value_usd) / nullif(max(a.volume_usd), 0) end as covered_share_of_volume
from shares s
join days_seen d using (month_start, dimension)
left join all_routes a using (month_start)
group by s.month_start, s.dimension, d.days_counted
