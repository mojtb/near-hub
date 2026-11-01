"""NEAR Intents: the 1Click token list, the public revenue page, and the Explorer API.

revenue.near.org is NEAR's own report. Its rendered tiles show 0 in plain HTML, but the full daily
series are embedded in the page, so the page is saved as received and parsed separately.

The Explorer API (JWT from partners.near-intents.org) covers 1Click swaps only, not all Intents. It
walks newest to oldest using the last deposit address as a cursor, one request per 5 seconds.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Dict

from ..http import HttpError
from ..parsers.revenue_page import parse as parse_revenue_page
from ..pipeline import Context, dataset
from ..settings import secret
from ._common import fetch

ONECLICK = "https://1click.chaindefuser.com"
EXPLORER = "https://explorer.near-intents.org"
REVENUE_PAGE = "https://revenue.near.org/"
EXPLORER_PAGE_SIZE = 1000
EXPLORER_NIGHTLY_PAGES = 200


@dataset("oneclick", "tokens")
def oneclick_tokens(ctx: Context) -> None:
    fetch(ctx, "oneclick", "tokens", "all", f"{ONECLICK}/v0/tokens")


@dataset("revenue_page", "page")
def revenue_page(ctx: Context) -> None:
    reply = fetch(ctx, "revenue_page", "html", "page", REVENUE_PAGE, ext="html")
    if reply is None:
        return
    parsed = parse_revenue_page(reply.content.decode("utf-8", "replace"))
    ctx.bronze.save_json("revenue_page", "parsed", "page", parsed, url=REVENUE_PAGE,
                         note="derived from html/page by ingest/parsers/revenue_page.py")


def _explorer_headers() -> Dict[str, str]:
    return {"Authorization": f"Bearer {secret('INTENTS_EXPLORER_JWT')}"}


@dataset("intents_explorer", "transactions", requires=("INTENTS_EXPLORER_JWT",))
def explorer_transactions(ctx: Context) -> None:
    """Swaps from newest to oldest. Stops at rows already seen, and resumes an unfinished backfill."""
    url = f"{EXPLORER}/api/v0/transactions"
    state = ctx.load_state("intents_explorer__transactions", {"oldest_cursor": None, "newest_seen": None, "backfill_done": False, "pages": 0})
    # Part 1: new swaps since the last run. Part 2: continue the historical backfill from its cursor.
    new_newest = None
    cursor = None
    for _ in range(EXPLORER_NIGHTLY_PAGES):
        params = {"numberOfTransactions": EXPLORER_PAGE_SIZE, "direction": "next"}
        if cursor:
            params.update(cursor)
        try:
            reply = ctx.http.get(url, params=params, headers=_explorer_headers())
        except HttpError as e:
            ctx.warn(str(e))
            break
        rows = reply.json()
        rows = rows.get("data", rows) if isinstance(rows, dict) else rows
        if not rows:
            break
        state["pages"] += 1
        ctx.bronze.save("intents_explorer", "transactions", f"page_{state['pages']:06d}", reply.content, url=url, params=params, rows=len(rows))
        if new_newest is None:
            new_newest = rows[0].get("createdAtTimestamp")
        last = rows[-1]
        cursor = {"lastDepositAddress": last.get("depositAddress"), "lastDepositMemo": last.get("depositMemo")}
        cursor = {k: v for k, v in cursor.items() if v}
        reached_seen = state["newest_seen"] and (last.get("createdAtTimestamp") or 0) <= state["newest_seen"]
        if reached_seen and state["backfill_done"]:
            break
        if reached_seen and state["oldest_cursor"]:
            cursor = state["oldest_cursor"]
        state["oldest_cursor"] = cursor
        if len(rows) < EXPLORER_PAGE_SIZE:
            state["backfill_done"] = True
            break
        ctx.save_state("intents_explorer__transactions", state)
    if new_newest:
        state["newest_seen"] = max(new_newest, state["newest_seen"] or 0)
    ctx.save_state("intents_explorer__transactions", state)
