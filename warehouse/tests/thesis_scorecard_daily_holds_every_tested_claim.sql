-- Every day of fct_thesis_scorecard_daily must hold every tested claim in dim_claim exactly once, tested or not yet,
-- so that a count of results by day never drops a claim without saying so.
select d.date_day, count(*) as claims, (select count(*) from {{ ref('dim_claim') }} where comparison is not null) as tested_claims
from {{ ref('fct_thesis_scorecard_daily') }} d
group by 1
having count(*) <> (select count(*) from {{ ref('dim_claim') }} where comparison is not null)
