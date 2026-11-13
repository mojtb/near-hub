-- A source that stops arriving used to go quiet: its tables kept their last values and every check still passed.
-- dq_freshness gives each dataset the most days it may fall behind the newest snapshot, and this fails once one passes
-- its limit. Datasets without a limit, a reading taken on request or a source being switched off, are not held to one.
select dataset, model, cadence, latest_data_day, as_of, days_behind, max_days_behind
from {{ ref('dq_freshness') }}
where is_stale
