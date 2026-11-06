-- A protocol must count once. The models merge slugs that share a DefiLlama id, so a row here means two ids carry one
-- series: DefiLlama re-listed a protocol under a new id, and someone has to decide which one stays.
-- 90% of shared days within 1% leaves room for a restatement on the night of the change. At the 2026-11-05 pin no
-- other pair of the 120 came close: the nearest matched on 3% of its shared days. Days when both read zero say nothing.
with pairs as (
    select
        a.protocol_slug as slug_a,
        b.protocol_slug as slug_b,
        count(*) as shared_days,
        count(*) filter (where abs(a.tvl_usd - b.tvl_usd) <= 0.01 * greatest(abs(a.tvl_usd), abs(b.tvl_usd))) as matching_days
    from {{ ref('fct_protocol_tvl_daily') }} a
    join {{ ref('fct_protocol_tvl_daily') }} b on a.date_day = b.date_day and a.protocol_slug < b.protocol_slug
    where a.tvl_usd <> 0 or b.tvl_usd <> 0
    group by 1, 2
)

select * from pairs
where shared_days >= 7 and matching_days >= 0.9 * shared_days
