with files as ({{ bronze_files('github__repos') }})

select
    snapshot_date,
    doc->>'full_name' as repo,
    cast(doc->>'stargazers_count' as bigint) as stars,
    cast(doc->>'forks_count' as bigint) as forks,
    cast(doc->>'open_issues_count' as bigint) as open_issues,
    cast(left(doc->>'pushed_at', 10) as date) as last_push_date,
    cast(left(doc->>'created_at', 10) as date) as created_date,
    {{ is_latest("doc->>'full_name'") }} as is_latest
from files
