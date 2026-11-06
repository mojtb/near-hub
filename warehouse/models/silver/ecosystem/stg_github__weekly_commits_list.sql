-- Commits and distinct authors per week on the default branch, counted from the commits list, for the 52 weeks before
-- each read. One method for every repository, and the only one for a repository GitHub's statistics answer with zeros.
-- The week still in progress when a read was taken is left out; a later read brings it in complete.
with files as ({{ bronze_files('github__commits_weekly') }}),

rows as (
    select snapshot_date, replace(file_key, '__', '/') as repo, {{ explode('doc') }} as w from files
),

typed as (
    select
        snapshot_date,
        repo,
        {{ unix_day("w->>'week'") }} as week_start,
        cast(w->>'total' as bigint) as commits,
        cast(w->>'authors' as bigint) as active_authors
    from rows
)

select *, {{ is_latest('repo, week_start') }} as is_latest
from typed
where week_start + 7 <= snapshot_date
