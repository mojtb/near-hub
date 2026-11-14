-- fct_thesis_scorecard_daily repeats the scorecard's tests in a form that takes a day. On its newest day it reads the
-- same data as fct_thesis_scorecard, so every tested claim must come out the same there: the same result, the same
-- value to nine decimals of its size, and the same day it rests on. A row here means a claim was changed in one model
-- and not in the other.
with newest as (
    select * from {{ ref('fct_thesis_scorecard_daily') }}
    where date_day = (select max(date_day) from {{ ref('fct_thesis_scorecard_daily') }})
)

select coalesce(s.claim_id, d.claim_id) as claim_id,
    s.status as scorecard_status, d.status as daily_status,
    s.value as scorecard_value, d.value as daily_value,
    s.as_of_date as scorecard_as_of_date, d.as_of_date as daily_as_of_date
from (select * from {{ ref('fct_thesis_scorecard') }} where status <> 'not_testable') s
full join newest d using (claim_id)
where s.claim_id is null or d.claim_id is null
   or s.status <> d.status
   or s.as_of_date is distinct from d.as_of_date
   or (s.value is null) <> (d.value is null)
   or abs(s.value - d.value) > 1e-9 * greatest(1, abs(s.value))
