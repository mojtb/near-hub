"""Developers and governance: GitHub repository stats, NEAR Catalog, and governance threads.

GitHub's statistics endpoints answer 202 while they compute, so a 202 is retried a few times. They also answer a repository
with over 10,000 commits with a year of zeros and an empty contributor list (anza-xyz/agave, 34,937 commits), so such a
repository's commits are counted from the commits list instead. Set GITHUB_TOKEN to raise the limit from 60 to 5,000 calls per hour.
"""
from __future__ import annotations

import gzip
import json
import time
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional

from ..http import HttpError
from ..pipeline import Context, dataset
from ..settings import BRONZE, read_registry, secret
from ._common import fetch

GITHUB = "https://api.github.com"
COMMITS_WEEKS = 52  # the same window as stats/commit_activity
COMMITS_PAGE_SIZE = 100
COMMITS_MAX_PAGES = 200  # 20,000 commits in a year; the busiest tracked repository makes about 5,000
CATALOG = "https://api.nearcatalog.xyz/projects"
GOV = "https://gov.near.org"
GOV_SEARCHES = ["HSP-", "inflation", "issuance", "fee switch", "buyback"]


def _github_headers() -> Dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = secret("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _github_stats(ctx: Context, dataset_name: str, repo: str, path: str) -> None:
    url = f"{GITHUB}/repos/{repo}/{path}"
    for attempt in range(5):
        try:
            reply = ctx.http.get(url, headers=_github_headers(), ok=(200, 202))
        except HttpError as e:
            ctx.warn(f"{repo}/{path}: {e}")
            return
        if reply.status == 200:
            ctx.bronze.save("github", dataset_name, repo.replace("/", "__"), reply.content, url=url)
            return
        time.sleep(3 * (attempt + 1))
    ctx.warn(f"{repo}/{path}: still computing after 5 tries")


@dataset("github", "repos")
def github_repos(ctx: Context) -> None:
    for r in read_registry("repos"):
        repo = r["repo"]
        fetch(ctx, "github", "repos", repo.replace("/", "__"), f"{GITHUB}/repos/{repo}", headers=_github_headers())


@dataset("github", "commit_activity")
def github_commit_activity(ctx: Context) -> None:
    """Commits per week for the last 52 weeks."""
    for r in read_registry("repos"):
        _github_stats(ctx, "commit_activity", r["repo"], "stats/commit_activity")


def week_start(day: date) -> date:
    """The Sunday on or before the day, which is how GitHub cuts its weekly statistics."""
    return day - timedelta(days=(day.weekday() + 1) % 7)


def commits_by_week(commits: Iterable[dict], first_week: date, weeks: int) -> List[dict]:
    """Commits and distinct authors per week, in the shape of stats/commit_activity plus an authors count.

    Weeks start on Sunday UTC and a commit falls in the week of its committer date, when it reached the branch.
    Author identities are counted and dropped.
    """
    totals: Dict[date, list] = {first_week + timedelta(days=7 * i): [0, set()] for i in range(weeks)}
    for c in commits:
        week = week_start(date.fromisoformat(c["commit"]["committer"]["date"][:10]))
        if week in totals:
            author = (c.get("author") or {}).get("login") or c["commit"]["author"].get("email") or c["commit"]["author"].get("name")
            totals[week][0] += 1
            totals[week][1].add(author)
    return [{"week": int(datetime(w.year, w.month, w.day, tzinfo=timezone.utc).timestamp()), "total": n, "authors": len(authors)}
            for w, (n, authors) in sorted(totals.items())]


def _stats_all_zero(ctx: Context, repo: str) -> bool:
    """True if this snapshot's commit_activity answer for the repository is a full year of zeros."""
    path = BRONZE / "github" / "commit_activity" / f"dt={ctx.snapshot}" / f"{repo.replace('/', '__')}.json.gz"
    if not path.exists():
        return False
    weeks = json.loads(gzip.decompress(path.read_bytes()))
    return bool(weeks) and sum(w.get("total", 0) for w in weeks) == 0


@dataset("github", "commits_weekly")
def github_commits_weekly(ctx: Context) -> None:
    """Commits per week on the default branch, counted from the commits list: one method for every repository.

    GitHub's statistic counts more than the default branch holds (about a quarter more for near/nearcore, which keeps
    release branches), and serves nothing at all for a repository with over 10,000 commits. This count is the same
    measure for every repository, and it is the only one for such a repository. It costs a call per 100 commits, so
    without a token only the repositories whose statistics came back as zeros are read.
    """
    today = date.fromisoformat(ctx.snapshot)
    first = week_start(today) - timedelta(weeks=COMMITS_WEEKS - 1)
    repos = [r["repo"] for r in read_registry("repos")]
    if not secret("GITHUB_TOKEN"):
        repos = [repo for repo in repos if _stats_all_zero(ctx, repo)]
    for repo in repos:
        url = f"{GITHUB}/repos/{repo}/commits"
        params = {"since": f"{first.isoformat()}T00:00:00Z", "per_page": COMMITS_PAGE_SIZE}
        commits: List[dict] = []
        complete = False
        for page in range(1, COMMITS_MAX_PAGES + 1):
            try:
                rows = ctx.http.get(url, params={**params, "page": page}, headers=_github_headers()).json()
            except HttpError as e:
                ctx.warn(f"{repo}/commits page {page}: {e}")
                break
            commits.extend(rows)
            if len(rows) < COMMITS_PAGE_SIZE:
                complete = True
                break
        if not complete:
            ctx.warn(f"{repo}/commits: the year was not read to the end, so nothing is stored; the next run tries again")
            continue
        weekly = commits_by_week(commits, first, COMMITS_WEEKS)
        ctx.bronze.save_json("github", "commits_weekly", repo.replace("/", "__"), weekly, url=url,
                             params={**params, "pages": page}, rows=len(weekly),
                             note=f"assembled: {len(commits)} commits on the default branch from the commits list, counted per "
                                  "week by committer date, with authors reduced to a count per week")


@dataset("nearcatalog", "projects")
def nearcatalog_projects(ctx: Context) -> None:
    fetch(ctx, "nearcatalog", "projects", "all", CATALOG, timeout=180)


@dataset("gov", "topics")
def gov_topics(ctx: Context) -> None:
    for query in GOV_SEARCHES:
        fetch(ctx, "gov", "search", query, f"{GOV}/search.json", params={"q": query})
    for topic_id in (42644, 42595, 41140, 41669):  # HSP-029, the 1.6% discussion, the 2.5% thread, Tokenomics 2.0
        fetch(ctx, "gov", "topics", str(topic_id), f"{GOV}/t/{topic_id}.json")
