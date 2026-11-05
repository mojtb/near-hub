-- The lists disagree on thin tokens, and that is handled: the value stays empty. A disagreement with real money on both sides
-- is different, because one list has a token badly wrong and a large position goes blank. Across 2026-11-01 to 11-05 the
-- largest gap with $100,000 or more behind Rhea's price was 4.1%, so this firing means someone should look at that token.
select snapshot_date, token_id, price_usd_oneclick, price_usd_rhea, price_gap_pct, depth_usd
from {{ ref('fct_token_prices') }}
where price_gap_pct > {{ var('price_disagreement_pct') }}
    and depth_usd >= 100000
