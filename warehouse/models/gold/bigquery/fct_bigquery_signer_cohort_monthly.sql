-- Do accounts come back? Every account that ever signed a transaction, placed in the month it first signed one, and
-- counted again in each later month in which it signed at least one. Counted in NEAR's public BigQuery dataset over
-- every transaction since genesis; no other source here can do it, because it needs each signer's whole history.
-- retained_share is the part of a cohort active in a later month. The month the read ended in is not a whole month.
with rows as (select * from {{ ref('stg_bigquery__signer_cohorts') }} where is_latest),

cohort as (select cohort_month, signers as cohort_signers from rows where active_month = cohort_month)

select
    r.cohort_month,
    r.active_month,
    cast(date_diff('month', r.cohort_month, r.active_month) as integer) as months_since_first,
    r.signers,
    c.cohort_signers,
    r.signers * 1.0 / nullif(c.cohort_signers, 0) as retained_share,
    r.active_month < cast(date_trunc('month', r.last_day) as date) or r.last_day = last_day(r.last_day) as is_active_month_complete,
    r.last_day as read_through
from rows r
left join cohort c using (cohort_month)
