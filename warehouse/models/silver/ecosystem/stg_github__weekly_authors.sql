-- Distinct contributors with at least one commit per week. GitHub's list covers the repo's top 100 authors.
with files as ({{ bronze_files('github__contributors') }}),

authors as (
    select snapshot_date, replace(file_key, '__', '/') as repo, {{ explode('doc') }} as a from files
),

weeks as (
    select snapshot_date, repo, {{ explode("a->'weeks'") }} as w from authors
),

typed as (
    select
        snapshot_date,
        repo,
        {{ unix_day("w->>'w'") }} as week_start,
        count(*) filter (where cast(w->>'c' as bigint) > 0) as active_authors
    from weeks
    group by all
)

select *, {{ is_latest('repo, week_start') }} as is_latest
from typed
