-- The share count built from registry/etf_nrr_history.csv must match Bitwise's page wherever a snapshot saw that day, and
-- net assets reported by SoSoValue, divided by NAV, must land within half a basket of it.
select date_day, shares_outstanding, fund_page_shares, reported_net_assets_usd / nav_usd as shares_from_reported_assets
from {{ ref('fct_etf_nrr_daily') }}
where shares_outstanding <> fund_page_shares
   or abs(reported_net_assets_usd / nav_usd - shares_outstanding) > 5000
