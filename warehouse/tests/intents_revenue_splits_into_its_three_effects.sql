-- fct_intents_unit_economics_monthly says revenue = volume x fee rate x capture rate, and that a month's change is the
-- sum of three effects. Both have to hold exactly on every month that carries the effects, or the split misleads.
select month_start, revenue_usd, volume_usd * fee_rate * capture_rate as rebuilt_revenue_usd,
    revenue_log_change, volume_log_effect + fee_rate_log_effect + capture_log_effect as summed_effects
from {{ ref('fct_intents_unit_economics_monthly') }}
where revenue_log_change is not null
  and (abs(volume_usd * fee_rate * capture_rate - revenue_usd) > 1e-6 * revenue_usd
       or abs(revenue_log_change - (volume_log_effect + fee_rate_log_effect + capture_log_effect)) > 1e-9)
