-- Commits and active authors per tracked repository per week, from GitHub. Covers the 52 weeks before each
-- read and accumulates across snapshots. This is a fixed repository list, not a whole-ecosystem count.
-- Two measures sit side by side. commits and active_authors are GitHub's own statistics, which count more than the
-- default branch holds (about a quarter more for near/nearcore, which keeps release branches) and come back as a
-- year of zeros with no contributors for a repository with over 10,000 commits (anza-xyz/agave). A year of zeros for
-- a repository that was pushed to inside that year is unknown activity, not none, so both are left empty there.
-- commits_default_branch and authors_default_branch are counted from the commits list with one method for every
-- repository, so they are the columns to compare repositories with.
with commits as (select * from {{ ref('stg_github__weekly_commits') }} where is_latest),

from_list as (select * from {{ ref('stg_github__weekly_commits_list') }} where is_latest),

pushed as (select repo, max(last_push_date) as last_push_date from {{ ref('fct_repo_snapshot') }} group by repo),

suspect as (
    select c.repo
    from commits c
    join pushed p using (repo)
    group by c.repo, p.last_push_date
    having sum(c.commits) = 0 and p.last_push_date >= min(c.week_start)
),

weeks as (
    select repo, week_start from commits
    union
    select repo, week_start from from_list
)

select
    w.week_start,
    w.repo,
    r.ecosystem,
    r.repo_group,
    case when s.repo is null then c.commits end as commits,
    case when s.repo is null then a.active_authors end as active_authors,
    l.commits as commits_default_branch,
    l.active_authors as authors_default_branch
from weeks w
left join commits c on c.repo = w.repo and c.week_start = w.week_start
left join from_list l on l.repo = w.repo and l.week_start = w.week_start
left join {{ ref('stg_github__weekly_authors') }} a on a.repo = w.repo and a.week_start = w.week_start and a.is_latest
left join {{ ref('repos') }} r on r.repo = w.repo
left join suspect s on s.repo = w.repo
