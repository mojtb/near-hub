-- Two routes to one balance: the token contract asked at the first block of a day, and FastNear's index of intents.near
-- read some hours into that same day. Where a day has both, the pool's wNEAR and its dollars in NEP-141 tokens must be
-- within half of each other. The pool moves in those hours, by 12% for the dollars on 2026-11-01, and over a whole day
-- neither has moved by 30% in the dashboard's series, so a wider gap means one of the two reads the wrong account, the
-- wrong contract or the wrong decimals. Only tokens both reads hold are summed. The other assets are left out: their
-- token units cannot be added, and one token's balance can move by more in those hours.
with pairs as (
    select
        r.date_day + 1 as snapshot_date,
        r.chosen_as,
        sum(r.amount_token) as at_first_block,
        sum(h.amount_token) as hours_later
    from {{ ref('stg_rpc__intents_pool_history') }} r
    join {{ ref('fct_wallet_holdings') }} h
        on h.account_id = 'intents.near' and h.token_id = r.contract_id and h.snapshot_date = r.date_day + 1
    where r.is_latest and r.error is null and r.token_standard = 'nep141' and r.chosen_as in ('wrapped_near', 'dollar_token')
    group by all
)

select *
from pairs
where abs(at_first_block - hours_later) > 0.5 * greatest(at_first_block, hours_later)
