"""NEAR Intents: the 1Click token list, the public revenue page, and the Explorer API.

revenue.near.org is NEAR's own report. Its rendered tiles show 0 in plain HTML, but the full daily
series are embedded in the page, so the page is saved as received and parsed separately.

The Explorer API (JWT from partners.near-intents.org) covers 1Click swaps only, not all Intents. Its rows
hold users' wallet addresses and run to about 14,000 a day, so each UTC day is walked once, counted and
thrown away: only the daily tally is stored. At one request per 5 seconds, history fills in over several nights.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from ..http import HttpError
from ..parsers.revenue_page import parse as parse_revenue_page
from ..pipeline import Context, dataset
from ..settings import read_registry, secret
from ._common import fetch

ONECLICK = "https://1click.chaindefuser.com"
EXPLORER = "https://explorer.near-intents.org"
REVENUE_PAGE = "https://revenue.near.org/"
EXPLORER_PAGE_SIZE = 1000
EXPLORER_RECENT_DAYS = 3  # statuses can still change, so these days are tallied again each night
EXPLORER_PAGES_PER_RUN = 500  # about 45 minutes at one request per 5.2 s
EXPLORER_EMPTY_DAYS_TO_STOP = 30  # this many empty days in a row is taken as the start of the history
EXPLORER_MIN_PAIR_USD = 1000.0  # smaller asset pairs on a day are summed into one (other) row
SIZE_BUCKETS = ((100.0, "under_100"), (1_000.0, "100_to_1k"), (10_000.0, "1k_to_10k"), (100_000.0, "10k_to_100k"), (float("inf"), "100k_and_over"))
SECONDS_PER_DAY = 86400


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


def tally_day(day: date, rows: List[dict], pages: int, known_recipients: Set[str]) -> Dict[str, Any]:
    """Count one UTC day of 1Click swaps. Only totals leave this function: no row and no wallet address.

    Channels cover every status. Pairs, sizes, fee recipients, routes and distinct wallets count finished swaps only.
    `appFees` entries are read as basis points of the amount paid in.
    """
    channels: Dict[tuple, List[float]] = defaultdict(lambda: [0, 0.0, 0.0, 0.0])
    pairs: Dict[tuple, List[float]] = defaultdict(lambda: [0, 0.0, 0.0])
    sizes: Dict[str, List[float]] = defaultdict(lambda: [0, 0.0])
    paid: Dict[str, List[float]] = defaultdict(lambda: [0, 0.0])
    routes: Dict[tuple, List[float]] = defaultdict(lambda: [0, 0.0])
    senders: Set[str] = set()
    recipients: Set[str] = set()
    for row in rows:
        amount_in, amount_out = float(row.get("amountInUsd") or 0), float(row.get("amountOutUsd") or 0)
        succeeded = row.get("status") == "SUCCESS"
        app_fee = 0.0
        for item in row.get("appFees") or []:
            fee_usd = (item.get("fee") or 0) / 10000 * amount_in
            app_fee += fee_usd
            if succeeded:
                entry = paid[item.get("recipient") if item.get("recipient") in known_recipients else "(other)"]
                entry[0] += 1
                entry[1] += fee_usd
        channel = channels[(row.get("referral"), row.get("status"))]
        channel[0] += 1
        channel[1] += amount_in
        channel[2] += amount_out
        channel[3] += app_fee
        if succeeded:
            pair = pairs[(row.get("originAsset"), row.get("destinationAsset"))]
            pair[0] += 1
            pair[1] += amount_in
            pair[2] += amount_out
            size = sizes[next(label for limit, label in SIZE_BUCKETS if amount_in < limit)]
            size[0] += 1
            size[1] += amount_in
            route = routes[(row.get("depositType"), row.get("recipientType"))]
            route[0] += 1
            route[1] += amount_in
            senders.update(row.get("senders") or [])
            if row.get("recipient"):
                recipients.add(row["recipient"])
    other = [0, 0.0, 0.0]
    kept = []
    for (origin, destination), (swaps, amount_in, amount_out) in sorted(pairs.items(), key=lambda kv: str(kv[0])):
        if amount_in >= EXPLORER_MIN_PAIR_USD:
            kept.append({"origin_asset": origin, "destination_asset": destination, "swaps": swaps,
                         "amount_in_usd": round(amount_in, 2), "amount_out_usd": round(amount_out, 2)})
        else:
            other = [other[0] + swaps, other[1] + amount_in, other[2] + amount_out]
    if other[0]:
        kept.append({"origin_asset": "(other)", "destination_asset": "(other)", "swaps": other[0],
                     "amount_in_usd": round(other[1], 2), "amount_out_usd": round(other[2], 2)})
    return {
        "day": day.isoformat(),
        "pages": pages,
        "swaps": len(rows),
        "senders": len(senders),
        "recipients": len(recipients),
        "channels": [{"referral": referral, "status": status, "swaps": v[0], "amount_in_usd": round(v[1], 2),
                      "amount_out_usd": round(v[2], 2), "app_fee_usd": round(v[3], 4)}
                     for (referral, status), v in sorted(channels.items(), key=lambda kv: str(kv[0]))],
        "pairs": kept,
        "sizes": [{"bucket": bucket, "swaps": v[0], "amount_in_usd": round(v[1], 2)} for bucket, v in sorted(sizes.items())],
        "fee_recipients": [{"recipient": who, "entries": v[0], "fee_usd": round(v[1], 4)} for who, v in sorted(paid.items())],
        "routes": [{"deposit_type": deposit, "recipient_type": recipient, "swaps": v[0], "amount_in_usd": round(v[1], 2)}
                   for (deposit, recipient), v in sorted(routes.items(), key=lambda kv: str(kv[0]))],
    }


def _walk_day(ctx: Context, day: date, pages_left: int) -> Optional[Tuple[List[dict], int]]:
    """Every row of one UTC day and the pages it took, or None if the page budget runs out first.

    The filter's bounds are exclusive and it can reach a little past them, so rows are checked against the day too.
    """
    start = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
    end = start + SECONDS_PER_DAY
    rows: Dict[str, dict] = {}
    cursor: Dict[str, str] = {}
    pages = 0
    while pages < pages_left:
        params = {"numberOfTransactions": EXPLORER_PAGE_SIZE, "direction": "next", "startTimestampUnix": start - 1, "endTimestampUnix": end, **cursor}
        page = ctx.http.get(f"{EXPLORER}/api/v0/transactions", params=params, headers=_explorer_headers()).json()
        pages += 1
        for row in page:
            if start <= row["createdAtTimestamp"] < end:
                rows[row["depositAddressAndMemo"]] = row
        if len(page) < EXPLORER_PAGE_SIZE:
            return list(rows.values()), pages
        last = page[-1]
        cursor = {k: v for k, v in (("lastDepositAddress", last.get("depositAddress")), ("lastDepositMemo", last.get("depositMemo"))) if v}
    return None


@dataset("intents_explorer", "daily_tally", requires=("INTENTS_EXPLORER_JWT",))
def explorer_daily_tally(ctx: Context) -> None:
    """Recent days again each night, then older days newest first, until the page budget runs out."""
    state = ctx.load_state("intents_explorer__daily_tally", {"days": {}, "history_starts": None})
    known = {e["account_id"] for e in read_registry("entities")}
    today = date.fromisoformat(ctx.snapshot)
    floor = date.fromisoformat(state["history_starts"]) if state["history_starts"] else None
    pages_left = EXPLORER_PAGES_PER_RUN
    empty_run = 0
    day = today - timedelta(days=1)
    while floor is None or day >= floor:
        key = day.isoformat()
        if key not in state["days"] or (today - day).days <= EXPLORER_RECENT_DAYS:
            try:
                walked = _walk_day(ctx, day, pages_left)
            except HttpError as e:
                ctx.warn(f"{key}: {e}")
                break
            if walked is None:
                break
            rows, pages = walked
            pages_left -= pages
            if rows:
                ctx.bronze.save_json("intents_explorer", "daily_tally", key, tally_day(day, rows, pages, known),
                                     url=f"{EXPLORER}/api/v0/transactions", params={"day": key, "pages": pages}, rows=len(rows),
                                     note="assembled: counted from this UTC day's rows; no row or wallet address is kept")
                ctx.bronze.flush()
            state["days"][key] = len(rows)
            ctx.save_state("intents_explorer__daily_tally", state)
        empty_run = empty_run + 1 if state["days"][key] == 0 else 0
        if floor is None and empty_run >= EXPLORER_EMPTY_DAYS_TO_STOP:
            state["history_starts"] = (day + timedelta(days=empty_run)).isoformat()
            ctx.save_state("intents_explorer__daily_tally", state)
            break
        day -= timedelta(days=1)
