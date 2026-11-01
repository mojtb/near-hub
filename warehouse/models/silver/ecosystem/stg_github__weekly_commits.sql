-- Commits per week for the last 52 weeks. file_key is owner__repo.
with files as ({{ bronze_files('github__commit_activity') }}),

rows as (
    select snapshot_date, replace(file_key, '__', '/') as repo, {{ explode('doc') }} as w from files
),

typed as (
    select
        snapshot_date,
        repo,
        {{ unix_day("w->>'week'") }} as week_start,
        cast(w->>'total' as bigint) as commits
    from rows
)

select *, {{ is_latest('repo, week_start') }} as is_latest
from typed
