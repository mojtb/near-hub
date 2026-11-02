-- 1Click is one route into NEAR Intents, so its finished volume should not pass the day's total for all of Intents.
select date_day, volume_usd, share_of_all_intents_volume
from {{ ref('fct_intents_1click_daily') }}
where share_of_all_intents_volume > 1.1
