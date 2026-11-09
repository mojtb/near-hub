-- Public Intents volume (NearBlocks) is part of all-route volume (revenue.near.org), but the two are different sources,
-- so on days when nearly everything was public the part can read a little above the whole: 88 days through 2026-04-20,
-- 7.7% at most. More than 10% above would mean one of the two has changed what it counts, as DefiLlama's series did on
-- 2026-09-01, and every share built on the pair would be wrong.
select date_day, volume_usd, public_volume_usd, public_volume_usd / volume_usd as public_share
from {{ ref('fct_intents_daily') }}
where public_volume_usd > 1.10 * volume_usd
