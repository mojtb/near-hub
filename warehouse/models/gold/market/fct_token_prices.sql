-- Point in time: one USD price per token per read, chosen from 1Click and Rhea, always by token id. A symbol is only a
-- contract's claim: usdc-4d51ec.launchpad.justhoot.near calls itself USDC. 1Click wins because nearly all its tokens carry a
-- market feed's id, while Rhea's list is one DEX's pools. A price of 0 or below means the list has no price, not a worthless token.
--
-- depth_usd says how much real money stands behind a Rhea price: the assets with a vetted price opposite the token, summed
-- over Rhea's pools. In a constant-product pool nobody can take out more than the other side, however much they sell.
with oneclick as (
    select
        snapshot_date,
        near_token_id as token_id,
        -- 1Click lists zec.omft.near, qtc.omft.near and prl.omft.near twice, with the same price and decimals.
        max(case when price_usd > 0 then price_usd end) as price_usd,
        max(price_date) as price_date,
        max(decimals) as decimals
    from {{ ref('stg_oneclick__tokens') }}
    where near_token_id is not null
    group by snapshot_date, near_token_id
),

rhea as (
    select snapshot_date, token_id, case when price_usd > 0 then price_usd end as price_usd, price_first_read, decimals
    from {{ ref('stg_rhea__token_prices') }}
),

listed as (
    select
        coalesce(o.snapshot_date, r.snapshot_date) as snapshot_date,
        coalesce(o.token_id, r.token_id) as token_id,
        o.price_usd as price_usd_oneclick,
        r.price_usd as price_usd_rhea,
        o.price_date as date_oneclick,
        r.price_first_read as date_rhea,
        o.decimals as decimals_oneclick,
        r.decimals as decimals_rhea,
        t.token_id is not null as in_registry,
        t.decimals as decimals_registry
    from oneclick o
    full join rhea r on r.snapshot_date = o.snapshot_date and r.token_id = o.token_id
    left join {{ ref('tokens') }} t on t.token_id = coalesce(o.token_id, r.token_id)
),

-- Tokens someone has looked at: 1Click prices them, or registry/tokens.csv lists them with evidence.
vetted as (
    select
        snapshot_date,
        token_id,
        coalesce(price_usd_oneclick, price_usd_rhea) as price_usd,
        coalesce(decimals_registry, decimals_oneclick, decimals_rhea) as decimals
    from listed
    where price_usd_oneclick is not null or (in_registry and price_usd_rhea is not null)
),

legs as (
    select
        l.snapshot_date,
        l.pool_id,
        l.token_id,
        try_cast(l.amount_raw as double) / pow(10, v.decimals) * v.price_usd as leg_usd
    from {{ ref('stg_rhea__pool_legs') }} l
    left join vetted v on v.snapshot_date = l.snapshot_date and v.token_id = l.token_id
),

opposite as (
    select
        snapshot_date,
        token_id,
        greatest(coalesce(sum(leg_usd) over (partition by snapshot_date, pool_id), 0) - coalesce(leg_usd, 0), 0) as opposite_usd
    from legs
),

depth as (
    select snapshot_date, token_id, sum(opposite_usd) as depth_usd
    from opposite
    group by snapshot_date, token_id
),

priced as (
    select
        l.snapshot_date,
        l.token_id,
        coalesce(l.price_usd_oneclick, l.price_usd_rhea) as price_usd,
        case when l.price_usd_oneclick is not null then 'oneclick' else 'rhea' end as price_source,
        case when l.price_usd_oneclick is not null then l.date_oneclick else l.date_rhea end as price_date,
        case when l.price_usd_oneclick is not null then l.decimals_oneclick else l.decimals_rhea end as price_decimals,
        l.price_usd_oneclick,
        l.price_usd_rhea,
        100.0 * abs(l.price_usd_oneclick - l.price_usd_rhea) / greatest(l.price_usd_oneclick, l.price_usd_rhea) as price_gap_pct,
        coalesce(d.depth_usd, 0) as depth_usd,
        l.price_usd_oneclick is not null or l.in_registry as is_vetted
    from listed l
    left join depth d on d.snapshot_date = l.snapshot_date and d.token_id = l.token_id
    where coalesce(l.price_usd_oneclick, l.price_usd_rhea) is not null
)

select * from priced

-- Native NEAR is on neither list. wrap.near redeems for it one to one, so it takes wrap.near's price.
union all
select
    snapshot_date,
    'native:near' as token_id,
    price_usd,
    price_source,
    price_date,
    price_decimals,
    price_usd_oneclick,
    price_usd_rhea,
    price_gap_pct,
    depth_usd,
    is_vetted
from priced
where token_id = 'wrap.near'
