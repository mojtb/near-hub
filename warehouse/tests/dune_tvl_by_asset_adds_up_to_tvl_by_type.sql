-- NEAR's dashboard splits the value held in Intents by asset and by public or confidential balance. On every day both
-- splits have, they add up to one figure.
with assets as (
    select date_day, sum(tvl_usd) as usd from {{ ref('fct_dune_intents_tvl_asset_daily') }} group by date_day
),

scopes as (
    select date_day, sum(tvl_usd) as usd from {{ ref('fct_dune_intents_tvl_daily') }} group by date_day
)

select date_day, a.usd as by_asset_usd, s.usd as by_scope_usd
from assets a
join scopes s using (date_day)
where abs(a.usd - s.usd) > 1e-6 * greatest(a.usd, s.usd, 1)
