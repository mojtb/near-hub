"""Dune, through its official API only. Reads the latest stored result of public queries.

Dune's free access is view-only and has no API, so this needs a key on a plan or active trial that
includes API access. Query ids come from NEAR's Intents dashboard and DefiLlama's adapter; see
registry/dune_queries.csv. Dated readings of the public dashboard page are kept separately in
bronze under dune_public, added by tools/record_dune_page.py.
"""
from __future__ import annotations

from ..http import HttpError
from ..pipeline import Context, dataset
from ..settings import read_registry, secret

API = "https://api.dune.com/api/v1"
PAGE_SIZE = 5000
MAX_PAGES = 40


@dataset("dune", "query_results", requires=("DUNE_API_KEY",))
def query_results(ctx: Context) -> None:
    headers = {"X-Dune-API-Key": secret("DUNE_API_KEY")}
    for q in read_registry("dune_queries"):
        query_id = q["query_id"]
        url = f"{API}/query/{query_id}/results"
        offset = 0
        for page in range(MAX_PAGES):
            params = {"limit": PAGE_SIZE, "offset": offset}
            try:
                reply = ctx.http.get(url, params=params, headers=headers, timeout=180)
            except HttpError as e:
                ctx.warn(f"query {query_id}: {e}")
                break
            payload = reply.json()
            rows = (payload.get("result") or {}).get("rows") or []
            ctx.bronze.save("dune", "query_results", f"{query_id}__p{page:03d}", reply.content, url=url, params=params, rows=len(rows))
            next_offset = payload.get("next_offset")
            if not next_offset or not rows:
                break
            offset = next_offset
