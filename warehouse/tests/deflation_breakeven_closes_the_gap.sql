-- At a scenario's break-even volume, the NEAR bought with captured fees must equal issuance less burn. If it does not,
-- the break-even in fct_deflation_scenarios is not a break-even.
select scenario_id, capture_case,
    issuance_near_per_day - burn_near_per_day as near_to_absorb,
    breakeven_volume_usd_per_day * fee_rate * capture_rate / price_usd as near_bought_at_breakeven
from {{ ref('fct_deflation_scenarios') }}
where abs(breakeven_volume_usd_per_day * fee_rate * capture_rate / price_usd - (issuance_near_per_day - burn_near_per_day))
      > 1e-9 * (issuance_near_per_day - burn_near_per_day)
   or abs(breakeven_volume_multiple * volume_usd_per_day - breakeven_volume_usd_per_day) > 1e-9 * breakeven_volume_usd_per_day
