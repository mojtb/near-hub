"""Developers and governance: GitHub repository stats, NEAR Catalog, and governance threads.

GitHub's statistics endpoints answer 202 while they compute, so a 202 is retried a few times.
Set GITHUB_TOKEN to raise the limit from 60 to 5,000 calls per hour.
"""
from __future__ import annotations

import time
from typing import Dict, Optional

from ..http import HttpError
from ..pipeline import Context, dataset
from ..settings import read_registry, secret
from ._common import fetch

GITHUB = "https://api.github.com"
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


@dataset("github", "contributors")
def github_contributors(ctx: Context) -> None:
    """Per contributor, the weeks with commits. Logins and profiles are dropped: only counts are needed."""
    for r in read_registry("repos"):
        repo = r["repo"]
        url = f"{GITHUB}/repos/{repo}/stats/contributors"
        for attempt in range(5):
            try:
                reply = ctx.http.get(url, headers=_github_headers(), ok=(200, 202))
            except HttpError as e:
                ctx.warn(f"{repo}: {e}")
                break
            if reply.status == 200:
                rows = [{"weeks": [{"w": w["w"], "c": w["c"]} for w in a.get("weeks", []) if w.get("c")]} for a in reply.json()]
                ctx.bronze.save_json("github", "contributors", repo.replace("/", "__"), rows, url=url, rows=len(rows),
                                     note="trimmed: author identities and empty weeks removed")
                break
            time.sleep(3 * (attempt + 1))
        else:
            ctx.warn(f"{repo}: still computing after 5 tries")


@dataset("nearcatalog", "projects")
def nearcatalog_projects(ctx: Context) -> None:
    fetch(ctx, "nearcatalog", "projects", "all", CATALOG, timeout=180)


@dataset("gov", "topics")
def gov_topics(ctx: Context) -> None:
    for query in GOV_SEARCHES:
        fetch(ctx, "gov", "search", query, f"{GOV}/search.json", params={"q": query})
    for topic_id in (42644, 42595, 41140, 41669):  # HSP-029, the 1.6% discussion, the 2.5% thread, Tokenomics 2.0
        fetch(ctx, "gov", "topics", str(topic_id), f"{GOV}/t/{topic_id}.json")
