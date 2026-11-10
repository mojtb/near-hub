-- 1Click swaps per UTC day, referral channel and status, from the Intents Explorer API.
-- USD values are kept for finished swaps only. For a swap that was refunded, failed or is still processing, the
-- Explorer's USD figure is the amount asked for, and nothing checks it: one refunded swap on 2026-07-28 reads
-- $29.99 trillion, and 245 on 2026-09-15 read $19.3 billion together. A sum over every status came to $30.0 trillion
-- against $6.5 billion of finished swaps. Silver keeps the figures as tallied; here an unfinished row keeps its count.
select
    c.date_day,
    c.referral,
    c.status,
    c.swaps,
    case when c.status = 'SUCCESS' then c.amount_in_usd end as amount_in_usd,
    case when c.status = 'SUCCESS' then c.amount_out_usd end as amount_out_usd,
    case when c.status = 'SUCCESS' then c.app_fee_usd end as app_fee_usd,
    coalesce(c.date_day >= {{ oneclick_daily_run_start() }}, false) as is_in_daily_run
from {{ ref('stg_intents_explorer__channels') }} c
where c.is_latest
