-- The prospectus says shares are created and redeemed in baskets of 10,000, so any other change means the share count
-- or the history file is wrong, or the basket size has changed.
select date_day, flow_shares
from {{ ref('fct_etf_nrr_daily') }}
where flow_shares % 10000 <> 0
