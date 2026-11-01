-- Point in time: the 100 largest holders per registry token, per snapshot. Protocol accounts are labelled;
-- other holders stay unlabelled, because this warehouse does not try to identify individuals.
select
    h.snapshot_date,
    h.token_id,
    t.symbol,
    h.holder_rank,
    h.holder_account_id,
    e.entity as holder_entity,
    e.category as holder_category,
    h.balance_raw,
    case when t.decimals is not null then cast(h.balance_raw as double) / pow(10, t.decimals) end as amount_token,
    h.balance_units * 1.0 / sum(h.balance_units) over (partition by h.snapshot_date, h.token_id) as share_of_top_100
from {{ ref('stg_fastnear__ft_top_holders') }} h
left join {{ ref('dim_token') }} t on t.token_id = h.token_id
left join {{ ref('entities') }} e on e.account_id = h.holder_account_id
