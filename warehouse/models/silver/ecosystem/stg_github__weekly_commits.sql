-- Commits per week for the last 52 weeks from GitHub's statistics endpoint. file_key is owner__repo.
-- The week still in progress when a read was taken is left out; a later read brings it in complete.
-- The statistic counts more than the default branch holds, and comes back as a year of zeros for a repository with
-- over 10,000 commits; stg_github__weekly_commits_list counts the default branch itself for every repository.
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
where week_start + 7 <= snapshot_date
