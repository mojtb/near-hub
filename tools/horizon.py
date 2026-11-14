"""The time horizon behind the break-even multiple: how long Intents volume would take to reach it.

One query, read by `tools/thesis.py` and exported by `tools/site_data.py`, so THESIS.md and the dashboard print the same
years from the same rows. It is arithmetic on measured figures and not a forecast: the break-even multiples in
`gold.fct_deflation_scenarios` (at the measured share of fees, today and at the end of HSP-029's ramp), and the growth of
Intents volume over the 30 days to the settled day against the same 30 days a year earlier (`gold.fct_intents_daily`).
The price, the fee rate and NEAR's share of fees are held as measured on the settled day.
"""
from __future__ import annotations

import math

HORIZON_SQL = """-- Years for Intents volume to reach the break-even multiple, at the growth measured over the last year and at
-- three round rates. The price, the fee rate and NEAR's share of fees are held as measured on the settled day, so
-- this is arithmetic and not a forecast.
with breakeven as (
    select scenario_id, as_of_date, breakeven_volume_multiple
    from gold.fct_deflation_scenarios
    where capture_case = 'measured'
),
settled as (
    select max(as_of_date) as settled_day from breakeven
),
volume as (
    select
        sum(volume_usd) filter (where date_day > settled_day - 30 and date_day <= settled_day) as volume_30d_usd,
        sum(volume_usd) filter (where date_day > settled_day - 395 and date_day <= settled_day - 365) as volume_30d_year_earlier_usd
    from gold.fct_intents_daily, settled
),
pace as (
    select 1 as pace_order, 'measured' as pace, volume_30d_usd / volume_30d_year_earlier_usd - 1 as growth_a_year from volume
    union all select 2, 'plus_25_pct', 0.25
    union all select 3, 'plus_50_pct', 0.50
    union all select 4, 'plus_100_pct', 1.00
)
select
    pace.pace,
    pace.growth_a_year,
    breakeven.scenario_id,
    breakeven.breakeven_volume_multiple,
    case
        when breakeven.breakeven_volume_multiple <= 1 then 0
        when pace.growth_a_year > 0 then ln(breakeven.breakeven_volume_multiple) / ln(1 + pace.growth_a_year)
    end as years_to_breakeven,
    volume.volume_30d_usd,
    volume.volume_30d_year_earlier_usd,
    settled.settled_day as as_of_date
from pace
cross join breakeven
cross join volume
cross join settled
order by pace.pace_order, breakeven.scenario_id;
"""


def years_to(multiple: float, growth_a_year: float) -> float | None:
    """Years of compound growth for a volume to become `multiple` times itself. None when it is not growing."""
    if multiple <= 1:
        return 0.0
    if growth_a_year <= 0:
        return None
    return math.log(multiple) / math.log(1 + growth_a_year)


def horizon(con) -> list[dict]:
    """The rows of HORIZON_SQL: one for each pace and scenario (`current`, `hsp029_end_state`).

    `years_to_breakeven` is None when the pace is not above zero, which a caller has to say in words.
    """
    cur = con.execute(HORIZON_SQL.rstrip().rstrip(";"))
    names = [d[0] for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]
