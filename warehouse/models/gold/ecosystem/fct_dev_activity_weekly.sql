-- Commits and active authors per tracked repository per week, from GitHub. Covers the 52 weeks before each
-- read and accumulates across snapshots. This is a fixed repository list, not a whole-ecosystem count.
-- GitHub's statistics endpoints can answer a very large repository with a full year of zeros and an empty
-- contributor list (anza-xyz/agave on 2026-11-01, pushed to that same day). A year of zeros for a repository
-- that was pushed to inside that year is unknown activity, not none, so both columns are left empty.
with commits as (select * from {{ ref('stg_github__weekly_commits') }} where is_latest),

pushed as (select repo, max(last_push_date) as last_push_date from {{ ref('fct_repo_snapshot') }} group by repo),

suspect as (
    select c.repo
    from commits c
    join pushed p using (repo)
    group by c.repo, p.last_push_date
    having sum(c.commits) = 0 and p.last_push_date >= min(c.week_start)
)

select
    c.week_start,
    c.repo,
    r.ecosystem,
    r.repo_group,
    case when s.repo is null then c.commits end as commits,
    case when s.repo is null then a.active_authors end as active_authors
from commits c
left join {{ ref('stg_github__weekly_authors') }} a on a.repo = c.repo and a.week_start = c.week_start and a.is_latest
left join {{ ref('repos') }} r on r.repo = c.repo
left join suspect s on s.repo = c.repo
