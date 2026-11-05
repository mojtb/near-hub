-- Point in time: tokens and native NEAR per tracked account, per snapshot. Symbol and decimals come from the registry through
-- dim_token where a token is listed, then from the token's own contract through ft_metadata, then from the price list that
-- prices it. A list counts whole tokens with its own decimals, so its price and its decimals belong together, and the lists'
-- decimals matched the contract on every token read so far. A contract that has answered, even with an error, is final: no
-- list fills in behind it. A token with none of the three stays empty. value_usd uses the price read in the same snapshot,
-- joined on token_id. value_status says why a row has no value.
with list_metadata as (
    -- One answer per token across every read. Decimals never varied between reads, and 1Click's figures win over Rhea's.
    select
        token_id,
        coalesce(max(symbol) filter (where source = 'oneclick'), max(symbol) filter (where source = 'rhea')) as symbol,
        coalesce(max(decimals) filter (where source = 'oneclick'), max(decimals) filter (where source = 'rhea')) as decimals
    from (
        select near_token_id as token_id, symbol, decimals, 'oneclick' as source
        from {{ ref('stg_oneclick__tokens') }} where near_token_id is not null and decimals is not null
        union all
        select token_id, symbol, decimals, 'rhea' as source
        from {{ ref('stg_rhea__token_prices') }} where decimals is not null
    )
    group by token_id
),

holdings as (
    select
        h.snapshot_date,
        h.account_id,
        h.token_id,
        coalesce(t.symbol, m.symbol, l.symbol, case when h.token_id = 'native:near' then 'NEAR' end) as symbol,
        h.balance_raw,
        case
            when h.token_id = 'native:near' then 24
            when t.decimals is not null then t.decimals
            when m.token_id is not null then m.decimals
            else l.decimals
        end as decimals,
        case
            when h.token_id = 'native:near' then 'native'
            when t.token_id is not null then 'registry'
            when m.token_id is not null then 'ft_metadata'
            when l.decimals is not null then 'price_list'
        end as metadata_source,
        h.last_update_height
    from {{ ref('stg_fastnear__holdings') }} h
    left join {{ ref('dim_token') }} t on t.token_id = h.token_id
    left join {{ ref('stg_rpc__ft_metadata') }} m on m.token_id = h.token_id and m.is_latest
    left join list_metadata l on l.token_id = h.token_id
    where try_cast(h.balance_raw as hugeint) > 0
),

converted as (
    select
        *,
        case
            when token_id = 'native:near' then {{ yocto_to_near('balance_raw') }}
            when decimals is not null then try_cast(balance_raw as double) / pow(10, decimals)
        end as amount_token
    from holdings
),

priced as (
    select
        h.*,
        p.price_usd,
        p.price_source,
        p.price_date,
        p.depth_usd as price_depth_usd,
        case
            when p.price_usd is null then 'no_price'
            when h.decimals is null then 'no_decimals'
            when h.decimals <> p.price_decimals then 'decimals_disagree'
            when p.price_gap_pct > {{ var('price_disagreement_pct') }} then 'sources_disagree'
            when not p.is_vetted and h.amount_token * p.price_usd > {{ var('price_depth_multiple') }} * p.depth_usd then 'thin_price'
            else 'valued'
        end as value_status
    from converted h
    left join {{ ref('fct_token_prices') }} p on p.snapshot_date = h.snapshot_date and p.token_id = h.token_id
)

select
    snapshot_date,
    account_id,
    token_id,
    symbol,
    balance_raw,
    amount_token,
    decimals,
    metadata_source,
    last_update_height,
    price_usd,
    price_source,
    price_date,
    price_depth_usd,
    case when value_status = 'valued' then amount_token * price_usd end as value_usd,
    value_status
from priced
