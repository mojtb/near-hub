"""NearBlocks: daily chain and Intents statistics, per-contract and per-wallet history.

Free tier: 6 calls per minute and 333 per day, so one nightly run (about 95 calls) takes about 17 minutes.
v3 daily endpoints return at most 365 days per call, so the warehouse keeps every snapshot and
history grows from there. Legacy /v1/charts is the only full daily history back to 2020.
"""
from __future__ import annotations

from typing import Dict

from ..pipeline import Context, dataset
from ..settings import read_registry, secret
from ._common import fetch, window_days

SOURCE = "nearblocks"
BASE = "https://api.nearblocks.io"

POINT_IN_TIME = {
    "stats": "/v3/stats",
    "stats_v1": "/v1/stats",
    "blocks_24h": "/v3/blocks/stats",
    "txns_24h": "/v3/txns/stats",
    "intents_totals": "/v3/intents/stats",
    "mpc_operators": "/v3/multichain/mpcs",
    "signatures_24h": "/v3/multichain/signatures/stats",
    "signer_totals": "/v3/signer-stats/total",
    "validators_info": "/v3/validators/info",  # seat price, last epoch's yield, total stake, validator counts
}

VALIDATORS_PER_PAGE = 100  # the endpoint's maximum
VALIDATOR_PAGE_LIMIT = 30  # 862 pools on 2026-11-10; stops a cursor that never ends
# Operators publish contact details, links and free text with their pool. Those stay out of bronze: the warehouse needs
# the figures, and the pool's account id already names it.
VALIDATOR_FIELDS_LEFT_OUT = ("name", "description", "email", "telegram", "twitter", "discord", "github", "url", "logo", "city")

# For these endpoints `limit` counts days, even when one day has many rows.
DAILY = {
    "txn_stats": "/v3/txn-stats",
    "address_stats": "/v3/address-stats",
    "signer_stats": "/v3/signer-stats",
    "block_stats": "/v3/block-stats",
    "price_stats": "/v3/price-stats",
    "tvl_stats": "/v3/tvl-stats",
    "intents_volume": "/v3/intents/volume-stats",
    "intents_swaps": "/v3/intents/swap-stats",
    "intents_accounts": "/v3/intents/account-stats",
    "intents_tokens": "/v3/intents/token-stats",
    "intents_chains": "/v3/intents/blockchain-stats",
    "intents_volume_by_chain": "/v3/intents/volume-stats/blockchains",
    "intents_volume_by_asset": "/v3/intents/volume-stats/assets",
}


def _headers() -> Dict[str, str]:
    key = secret("NEARBLOCKS_API_KEY")
    return {"Authorization": f"Bearer {key}"} if key else {}


def _register_point_in_time(name: str, path: str) -> None:
    @dataset(SOURCE, name)
    def run(ctx: Context) -> None:
        fetch(ctx, SOURCE, name, "all", f"{BASE}{path}", headers=_headers())


def _register_daily(name: str, path: str) -> None:
    @dataset(SOURCE, name)
    def run(ctx: Context) -> None:
        params = {"limit": window_days(ctx, SOURCE, name)}
        fetch(ctx, SOURCE, name, "all", f"{BASE}{path}", params=params, headers=_headers())


for _name, _path in POINT_IN_TIME.items():
    _register_point_in_time(_name, _path)
for _name, _path in DAILY.items():
    _register_daily(_name, _path)


@dataset(SOURCE, "charts_v1")
def charts_v1(ctx: Context) -> None:
    fetch(ctx, SOURCE, "charts_v1", "all", f"{BASE}/v1/charts", headers=_headers(),
          note="legacy endpoint; full daily history from 2020-07-21")


@dataset(SOURCE, "validators")
def validators(ctx: Context) -> None:
    """Every staking pool with its delegator count, fee, stake and country. NearBlocks shows only the current state, so
    each night has to save it; a missed night can still be read from each pool's own views at a past block. The list is
    saved whole or not at all, because half a list would read as pools that left."""
    url = f"{BASE}/v3/validators"
    rows, cursor = [], None
    for _ in range(VALIDATOR_PAGE_LIMIT):
        params = {"limit": VALIDATORS_PER_PAGE, **({"next": cursor} if cursor else {})}
        page = ctx.http.get(url, params=params, headers=_headers()).json()
        rows += [{k: v for k, v in row.items() if k not in VALIDATOR_FIELDS_LEFT_OUT} for row in page.get("data") or []]
        cursor = (page.get("meta") or {}).get("next_page")
        if not cursor:
            break
    else:
        ctx.warn(f"stopped after {VALIDATOR_PAGE_LIMIT} pages with more to read")
    if not rows:
        raise ValueError("the validator list came back empty")
    ctx.bronze.save_json(SOURCE, "validators", "all", rows, url=url, params={"limit": VALIDATORS_PER_PAGE}, rows=len(rows),
                         note="assembled: every page of the list; trimmed: operators' contact details, links and free text are left out")


@dataset(SOURCE, "ft_transfer_stats")
def ft_transfer_stats(ctx: Context) -> None:
    """Daily transfers, amount moved, and unique senders and receivers per registry token. The endpoint returns only the
    newest 365 days and takes no date, so the history can only grow from the first night it is read."""
    for t in read_registry("tokens"):
        token = t["token_id"]
        params = {"limit": window_days(ctx, SOURCE, "ft_transfer_stats", token)}
        fetch(ctx, SOURCE, "ft_transfer_stats", token, f"{BASE}/v3/fts/{token}/stats/transfers", params=params, headers=_headers())


@dataset(SOURCE, "contract_txns")
def contract_txns(ctx: Context) -> None:
    """Daily transactions and unique callers per registry contract."""
    for e in read_registry("entities"):
        if e["track_contract_stats"] == "1":
            account = e["account_id"]
            params = {"limit": window_days(ctx, SOURCE, "contract_txns", account)}
            fetch(ctx, SOURCE, "contract_txns", account, f"{BASE}/v3/accounts/{account}/stats/txns",
                  params=params, headers=_headers())


@dataset(SOURCE, "wallet_balance")
def wallet_balance(ctx: Context) -> None:
    """Daily balance history per registry wallet; checks the FastNear running balance."""
    for e in read_registry("entities"):
        if e["crawl_transfers"] == "1":
            account = e["account_id"]
            params = {"limit": window_days(ctx, SOURCE, "wallet_balance", account)}
            fetch(ctx, SOURCE, "wallet_balance", account, f"{BASE}/v3/accounts/{account}/stats/balance",
                  params=params, headers=_headers())
