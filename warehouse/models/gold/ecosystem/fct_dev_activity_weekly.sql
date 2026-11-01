-- Commits and active authors per tracked repository per week, from GitHub. Covers the 52 weeks before each
-- read and accumulates across snapshots. This is a fixed repository list, not a whole-ecosystem count.
select
    c.week_start,
    c.repo,
    r.ecosystem,
    r.repo_group,
    c.commits,
    a.active_authors
from {{ ref('stg_github__weekly_commits') }} c
left join {{ ref('stg_github__weekly_authors') }} a on a.repo = c.repo and a.week_start = c.week_start and a.is_latest
left join {{ ref('repos') }} r on r.repo = c.repo
where c.is_latest
