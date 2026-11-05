-- A valued row uses a price that passed every rule: the list counts whole tokens with the holding's decimals, the two lists
-- are close enough, and a token nobody has vetted stays within what stands behind its price.
select h.snapshot_date, h.account_id, h.token_id, h.decimals, p.price_decimals, p.price_gap_pct, p.is_vetted, p.depth_usd, h.value_usd
from {{ ref('fct_wallet_holdings') }} h
join {{ ref('fct_token_prices') }} p on p.snapshot_date = h.snapshot_date and p.token_id = h.token_id
where h.value_status = 'valued'
    and (
        h.decimals <> p.price_decimals
        or p.price_gap_pct > {{ var('price_disagreement_pct') }}
        or (not p.is_vetted and h.value_usd > {{ var('price_depth_multiple') }} * p.depth_usd * (1 + 1e-9))
    )
