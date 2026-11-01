-- Stars, forks and last push per tracked repository, per read.
select
    g.snapshot_date,
    g.repo,
    r.ecosystem,
    r.repo_group,
    g.stars,
    g.forks,
    g.open_issues,
    g.last_push_date,
    g.created_date
from {{ ref('stg_github__repos') }} g
left join {{ ref('repos') }} r on r.repo = g.repo
