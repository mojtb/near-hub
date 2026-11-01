"""NEAR Intents: the 1Click token list, the public revenue page, and the Explorer API.

revenue.near.org is NEAR's own report. Its rendered tiles show 0 in plain HTML, but the full daily
series are embedded in the page, so the page is saved as received and parsed separately.

The Explorer API (JWT from partners.near-intents.org) covers 1Click swaps only, not all Intents. It
walks newest to oldest using the last deposit address as a cursor, one request per 5 seconds.
"""
from __future__ import annotations

from typing import Dict, Optional

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
    """Two walks, both from newer to older: first any swaps new since the last run, then the unfinished backfill.

    The API answers an array, newest first. `direction=next` means older, and the cursor is the last row's
    deposit address and memo. This has not run against the live API yet, because it needs a JWT.
    """
    state = ctx.load_state("intents_explorer__transactions",
                           {"newest_seen": 0, "backfill_cursor": None, "backfill_done": False, "pages": 0})

    def walk(cursor, stop_at, pages_left):
        newest, last_cursor = 0, cursor
        for _ in range(pages_left):
            rows = _explorer_page(ctx, last_cursor, state)
            if rows is None:
                return newest, last_cursor, False
            if not rows:
                return newest, last_cursor, True
            newest = max(newest, max(int(r.get("createdAtTimestamp") or 0) for r in rows))
            last = rows[-1]
            last_cursor = {k: v for k, v in (("lastDepositAddress", last.get("depositAddress")),
                                             ("lastDepositMemo", last.get("depositMemo"))) if v}
            ctx.save_state("intents_explorer__transactions", state)
            if len(rows) < EXPLORER_PAGE_SIZE or int(last.get("createdAtTimestamp") or 0) <= stop_at:
                return newest, last_cursor, True
        return newest, last_cursor, False

    first_run = state["newest_seen"] == 0
    newest, first_cursor, reached_end = walk(None, state["newest_seen"], EXPLORER_NIGHTLY_PAGES // 2)
    if first_run:
        # With nothing seen before, the first walk is the start of the backfill.
        state["backfill_cursor"], state["backfill_done"] = first_cursor, reached_end
    state["newest_seen"] = max(state["newest_seen"], newest)
    if not state["backfill_done"]:
        _, cursor, finished = walk(state["backfill_cursor"], 0, EXPLORER_NIGHTLY_PAGES // 2)
        state["backfill_cursor"], state["backfill_done"] = cursor, finished
    ctx.save_state("intents_explorer__transactions", state)


def _explorer_page(ctx: Context, cursor, state) -> Optional[list]:
    url = f"{EXPLORER}/api/v0/transactions"
    params = {"numberOfTransactions": EXPLORER_PAGE_SIZE, "direction": "next", **(cursor or {})}
    try:
        reply = ctx.http.get(url, params=params, headers=_explorer_headers())
    except HttpError as e:
        ctx.warn(str(e))
        return None
    rows = reply.json()
    if rows:
        state["pages"] += 1
        ctx.bronze.save("intents_explorer", "transactions", f"page_{state['pages']:06d}", reply.content,
                        url=url, params=params, rows=len(rows))
    return rows
