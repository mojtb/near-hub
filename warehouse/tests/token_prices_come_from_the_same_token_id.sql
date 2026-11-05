-- Each price traces back to its own list under the same token id in the same read, and 1Click wins wherever it has a price.
-- A join on symbol fails this: usdc-4d51ec.launchpad.justhoot.near calls itself USDC, and 1Click does not list that contract.
with oneclick as (
    select snapshot_date, near_token_id as token_id, max(case when price_usd > 0 then price_usd end) as price_usd
    from {{ ref('stg_oneclick__tokens') }}
    where near_token_id is not null
    group by snapshot_date, near_token_id
),

rhea as (
    select snapshot_date, token_id, case when price_usd > 0 then price_usd end as price_usd
    from {{ ref('stg_rhea__token_prices') }}
),

prices as (
    select snapshot_date, case when token_id = 'native:near' then 'wrap.near' else token_id end as list_token_id, token_id, price_usd, price_source, price_date
    from {{ ref('fct_token_prices') }}
),

price_rows as (
    select p.token_id, p.snapshot_date, p.price_usd, p.price_source, p.price_date, o.price_usd as oneclick_usd, r.price_usd as rhea_usd
    from prices p
    left join oneclick o on o.snapshot_date = p.snapshot_date and o.token_id = p.list_token_id
    left join rhea r on r.snapshot_date = p.snapshot_date and r.token_id = p.list_token_id
    where p.price_date > p.snapshot_date
        or p.price_usd is distinct from coalesce(o.price_usd, r.price_usd)
        or p.price_source <> case when o.price_usd is not null then 'oneclick' else 'rhea' end
),

holding_rows as (
    select h.token_id, h.snapshot_date, h.price_usd, h.price_source, h.price_date, null::double as oneclick_usd, null::double as rhea_usd
    from {{ ref('fct_wallet_holdings') }} h
    left join {{ ref('fct_token_prices') }} p on p.snapshot_date = h.snapshot_date and p.token_id = h.token_id
    where h.price_usd is distinct from p.price_usd
        or h.price_source is distinct from p.price_source
        or h.price_date is distinct from p.price_date
)

select * from price_rows
union all
select * from holding_rows
