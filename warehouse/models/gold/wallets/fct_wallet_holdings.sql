-- Point in time: tokens and native NEAR per tracked account, per snapshot. amount_token needs known decimals.
select
    h.snapshot_date,
    h.account_id,
    h.token_id,
    coalesce(t.symbol, case when h.token_id = 'native:near' then 'NEAR' end) as symbol,
    h.balance_raw,
    case
        when h.token_id = 'native:near' then {{ yocto_to_near('h.balance_raw') }}
        when t.decimals is not null then cast(h.balance_raw as double) / pow(10, t.decimals)
    end as amount_token,
    h.last_update_height
from {{ ref('stg_fastnear__holdings') }} h
left join {{ ref('dim_token') }} t on t.token_id = h.token_id
where try_cast(h.balance_raw as hugeint) > 0
