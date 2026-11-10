-- Each month's channels in fct_intents_channel_economics_monthly must account for all of that month's volume and fees.
select month_start, sum(share_of_volume) as volume_shares, sum(share_of_fees) as fee_shares
from {{ ref('fct_intents_channel_economics_monthly') }}
group by 1
having abs(sum(share_of_volume) - 1) > 1e-9 or (sum(app_fee_usd) > 0 and abs(sum(share_of_fees) - 1) > 1e-9)
