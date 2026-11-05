-- Point in time: tokens and native NEAR per tracked account, per snapshot. Symbol and decimals come from the registry through
-- dim_token where a token is listed, otherwise from its own contract's ft_metadata. A token with neither stays empty.
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
)

select
    snapshot_date,
    account_id,
    token_id,
    symbol,
    balance_raw,
    case
        when token_id = 'native:near' then {{ yocto_to_near('balance_raw') }}
        when decimals is not null then cast(balance_raw as double) / pow(10, decimals)
    end as amount_token,
    decimals,
    metadata_source,
    last_update_height
from holdings
