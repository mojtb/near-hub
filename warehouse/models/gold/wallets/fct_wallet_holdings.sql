-- Point in time: tokens and native NEAR per tracked account, per snapshot. Symbol and decimals come from the registry through
-- dim_token where a token is listed, otherwise from its own contract's ft_metadata. A token with neither stays empty.
-- value_usd uses the price read in the same snapshot, joined on token_id. value_status says why a row has no value.
with holdings as (
    select
        h.snapshot_date,
        h.account_id,
        h.token_id,
        coalesce(t.symbol, m.symbol, case when h.token_id = 'native:near' then 'NEAR' end) as symbol,
        h.balance_raw,
        case when h.token_id = 'native:near' then 24 else coalesce(t.decimals, m.decimals) end as decimals,
        case
            when h.token_id = 'native:near' then 'native'
            when t.token_id is not null then 'registry'
            when m.decimals is not null or m.symbol is not null then 'ft_metadata'
        end as metadata_source,
        h.last_update_height
    from {{ ref('stg_fastnear__holdings') }} h
    left join {{ ref('dim_token') }} t on t.token_id = h.token_id
    left join {{ ref('stg_rpc__ft_metadata') }} m on m.token_id = h.token_id and m.is_latest
    where try_cast(h.balance_raw as hugeint) > 0
),

converted as (
    select
        *,
        case
            when token_id = 'native:near' then {{ yocto_to_near('balance_raw') }}
            when decimals is not null then cast(balance_raw as double) / pow(10, decimals)
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
