-- fct_intents_1click_channel_daily keeps USD values for finished swaps only. The Explorer's USD figure for a swap that
-- did not finish is the amount asked for, which nothing checks: one refunded swap on 2026-07-28 reads $29.99 trillion.
-- So a row in any other status must carry no USD. A finished row must be possible: nothing negative, fees within the
-- value paid in, and no channel above the day's total for all of Intents, with the 10% that
-- oneclick_volume_within_all_intents allows the day.
select c.date_day, c.referral, c.status, c.swaps, c.amount_in_usd, c.amount_out_usd, c.app_fee_usd, i.volume_usd as all_intents_volume_usd
from {{ ref('fct_intents_1click_channel_daily') }} c
left join {{ ref('fct_intents_daily') }} i using (date_day)
where (c.status is distinct from 'SUCCESS'
       and (c.amount_in_usd is not null or c.amount_out_usd is not null or c.app_fee_usd is not null))
   or (c.status = 'SUCCESS'
       and (c.amount_in_usd < 0 or c.amount_out_usd < 0 or c.app_fee_usd < 0
            or c.app_fee_usd > c.amount_in_usd
            or c.amount_in_usd > 1.1 * i.volume_usd))
