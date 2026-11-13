-- NEAR's dashboard splits the same all-route volume by blockchain and by asset, so on every day the two splits add up
-- to one figure. A gap means a widget was read in part, or that the two come from different readings.
with chains as (
    select date_day, sum(volume_usd) as usd from {{ ref('fct_dune_intents_chain_daily') }} group by date_day
),

assets as (
    select date_day, sum(volume_usd) as usd from {{ ref('fct_dune_intents_asset_daily') }} group by date_day
)

select date_day, c.usd as by_chain_usd, a.usd as by_asset_usd
from chains c
join assets a using (date_day)
where abs(c.usd - a.usd) > 1e-6 * greatest(c.usd, a.usd, 1)
