-- A gap beyond tolerance is fine, and often interesting, but it must have a written explanation.
select check_id, subject, diff_pct, tolerance_pct
from {{ ref('dq_reconciliation') }}
where status = 'differs' and explanation is null
