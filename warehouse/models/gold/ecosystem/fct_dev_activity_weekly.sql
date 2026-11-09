-- Commits and active authors per tracked repository per week, counted from GitHub's commits list on each repository's
-- default branch, by committer date, with one method for every repository. Covers the 52 weeks before each read and
-- accumulates across snapshots. This is a fixed repository list, not a whole-ecosystem count.
-- GitHub's own weekly statistic is not used: it counts more than the default branch holds (about a third more for
-- near/nearcore, which keeps release branches, and less for some repositories), and it returns a year of zeros for a
-- repository with over 10,000 commits (anza-xyz/agave). Silver keeps it, and dq_reconciliation compares it for nearcore.
with from_list as (select * from {{ ref('stg_github__weekly_commits_list') }} where is_latest)

select
    l.week_start,
    l.repo,
    r.ecosystem,
    r.repo_group,
    l.commits as commits_default_branch,
    l.active_authors as authors_default_branch
from from_list l
left join {{ ref('repos') }} r on r.repo = l.repo
