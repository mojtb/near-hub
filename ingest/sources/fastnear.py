"""FastNear indexed APIs: token holdings, top token holders, transaction counts, wallet transfers.

The transfers crawl is the heart of the wallet layer. It walks oldest to newest with `resume_token`
and remembers its position, so each night fetches only what is new. The last page is re-read on
purpose in case rows were added to it; the warehouse removes the duplicates.
"""
from __future__ import annotations

from typing import Dict, Optional

from ..http import HttpError
from ..pipeline import Context, dataset
from ..settings import read_registry, secret
from ._common import fetch

SOURCE = "fastnear"
API = "https://api.fastnear.com"
TX = "https://tx.main.fastnear.com"
TRANSFERS = "https://transfers.main.fastnear.com"
PAGE_SIZE = 100  # the API's maximum
NIGHTLY_PAGE_LIMIT = 120  # per wallet; a long first crawl continues on later runs


def _headers() -> Optional[Dict[str, str]]:
    key = secret("FASTNEAR_API_KEY")
    return {"Authorization": f"Bearer {key}"} if key else None


@dataset(SOURCE, "account_full")
def account_full(ctx: Context) -> None:
    """Tokens, NFTs and staking pools per tracked account. Point in time: cannot be backfilled."""
    for e in read_registry("entities"):
        if e["track_holdings"] == "1":
            account = e["account_id"]
            fetch(ctx, SOURCE, "account_full", account, f"{API}/v1/account/{account}/full", headers=_headers())


@dataset(SOURCE, "ft_top_holders")
def ft_top_holders(ctx: Context) -> None:
    """Largest holders per registry token. Point in time: cannot be backfilled."""
    for t in read_registry("tokens"):
        if t["track_holders"] == "1":
            token = t["token_id"]
            fetch(ctx, SOURCE, "ft_top_holders", token, f"{API}/v1/ft/{token}/top", headers=_headers())


@dataset(SOURCE, "tx_counts")
def tx_counts(ctx: Context) -> None:
    """Cumulative transaction count per registry account. Differences between nights give activity."""
    rows = []
    for e in read_registry("entities"):
        account = e["account_id"]
        try:
            reply = ctx.http.post(f"{TX}/v0/account", {"account_id": account, "limit": 1}, headers=_headers())
        except HttpError as err:
            ctx.warn(f"{account}: {err}")
            continue
        rows.append({"account_id": account, "txs_count": reply.json().get("txs_count")})
    ctx.bronze.save_json(SOURCE, "tx_counts", "registry", rows, url=f"{TX}/v0/account", method="POST", rows=len(rows),
                         note="assembled: txs_count from one call per registry account")


@dataset(SOURCE, "transfers")
def transfers(ctx: Context) -> None:
    state: Dict[str, dict] = ctx.load_state("fastnear__transfers", {})
    for e in read_registry("entities"):
        if e["crawl_transfers"] != "1":
            continue
        account = e["account_id"]
        position = state.setdefault(account, {"resume_token": None, "pages": 0, "rows": 0, "at_tail": False})
        for _ in range(NIGHTLY_PAGE_LIMIT):
            body = {"account_id": account, "limit": PAGE_SIZE, "desc": False}
            if position["resume_token"]:
                body["resume_token"] = position["resume_token"]
            try:
                reply = ctx.http.post(f"{TRANSFERS}/v0/transfers", body, headers=_headers())
            except HttpError as err:
                ctx.warn(f"{account}: {err}")
                break
            payload = reply.json()
            rows = payload.get("transfers") or []
            if not rows:
                position["at_tail"] = True
                break
            position["pages"] += 1
            ctx.bronze.save(SOURCE, "transfers", f"{account}__p{position['pages']:06d}", reply.content,
                            url=f"{TRANSFERS}/v0/transfers", method="POST", params={"body": body}, rows=len(rows))
            token = payload.get("resume_token")
            if not token or len(rows) < PAGE_SIZE:
                position["at_tail"] = True
                break
            position["resume_token"] = token
            position["rows"] += len(rows)
            position["at_tail"] = False
            ctx.save_state("fastnear__transfers", state)
        ctx.save_state("fastnear__transfers", state)
