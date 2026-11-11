"""The Bitwise NEAR ETF (NRR): the fund's own figures, and its NEAR as seen on chain.

Flow is the change in shares times NAV. The fund's page shows only the current share count, so each night has to save
it. The chain keeps its own record: the page lists the trust's wallets, nearly all of them delegate to one staking pool,
and one view call at a past block reads the whole pool, so a missed night can still be read later.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set

from ..parsers.nrr_page import EXTRAS as NRR_PAGE_EXTRAS, parse as parse_nrr_page
from ..pipeline import Context, Skip, dataset
from .rpc import ARCHIVAL, _view

NRR_PAGE = "https://nrretf.com/"
POOL = "bitwise_2.poolv1.near"
FIRST_BLOCK_DAY = date(2026, 9, 28)  # the first block of this day closes the last day before the fund's first deposit
RECENT_DAYS = 3  # read again each night, in case the page lists a new wallet late
ACCOUNTS_PER_CALL = 200


@dataset("nrr_fund", "figures")
def nrr_figures(ctx: Context) -> None:
    """Keep the page's figures and wallet list, not the page, because Bitwise's terms limit copying site content."""
    page = ctx.http.get(NRR_PAGE, headers={"Accept": "text/html"})
    figures = parse_nrr_page(page.content.decode("utf-8", "replace"))
    missing = [name for name in NRR_PAGE_EXTRAS if figures[name] is None]
    if missing:
        ctx.warn(f"the page no longer shows: {', '.join(missing)}")
    ctx.bronze.save_json("nrr_fund", "figures", "page", figures, url=NRR_PAGE, rows=len(figures["wallets"]),
                         note="assembled: figures read from the page's embedded data; the page itself is not kept")
    seen = set(ctx.load_state("nrr_fund__wallets", []))
    ctx.save_state("nrr_fund__wallets", sorted(seen | {w["address"] for w in figures["wallets"]}))


def _read_pool(ctx: Context, height: int, wallets: Set[str]) -> Optional[Dict[str, Any]]:
    """Every delegator at one block. Other delegators are people's own wallets, so only their total is kept."""
    kept: List[Dict[str, str]] = []
    others = delegators = start = 0
    while True:
        view = _view(ctx, POOL, "get_accounts", {"from_index": start, "limit": ACCOUNTS_PER_CALL}, block_id=height)
        if view is None:
            return None
        for account in view["result"]:
            delegators += 1
            if account["account_id"] in wallets:
                kept.append({"account_id": account["account_id"], "staked": account["staked_balance"], "unstaked": account["unstaked_balance"]})
            else:
                others += int(account["staked_balance"]) + int(account["unstaked_balance"])
        if len(view["result"]) < ACCOUNTS_PER_CALL:
            return {"height": height, "delegators": delegators, "other_delegators_yocto": str(others), "wallets": kept}
        start += ACCOUNTS_PER_CALL


@dataset("rpc", "nrr_pool_daily")
def nrr_pool_daily(ctx: Context) -> None:
    """The fund's wallets in its pool at the first block of each UTC day, which closes the day before."""
    wallets = set(ctx.load_state("nrr_fund__wallets", []))
    if not wallets:
        raise Skip("no wallet list yet: run nrr_fund/figures first")
    heights: Dict[str, int] = ctx.load_state("rpc__block_day", {})
    done = set(ctx.load_state("rpc__nrr_pool_daily", []))
    today = date.fromisoformat(ctx.snapshot)
    rows: List[Dict[str, Any]] = []
    day = FIRST_BLOCK_DAY
    while day <= today:
        key = day.isoformat()
        if key not in done or (today - day).days < RECENT_DAYS:
            if key not in heights:
                ctx.warn(f"{key}: no block height known yet")
            else:
                read = _read_pool(ctx, heights[key], wallets)
                if read:
                    rows.append({"closes_day": (day - timedelta(days=1)).isoformat(), **read})
                    done.add(key)
        day += timedelta(days=1)
    if rows:
        ctx.bronze.save_json("rpc", "nrr_pool_daily", f"from_{rows[0]['closes_day']}", rows, url=ARCHIVAL, method="POST", rows=len(rows),
                             params={"contract": POOL, "view": "get_accounts"},
                             note="assembled: the wallets Bitwise lists for NRR at the first block of each UTC day, read at past blocks; other delegators kept only as a total")
        ctx.save_state("rpc__nrr_pool_daily", sorted(done))
