"""What the NEAR Intents contract held of named tokens at past blocks, read from the chain itself.

`intents.near` keeps every deposit in its own account, public and confidential balances alike, so a token contract's
answer about that one account is the whole pool's balance of that token. A token that follows NEP-141 answers
`ft_balance_of`. The tokens bridged through HOT are NEP-245 balances inside one contract, which answers
`mt_batch_balance_of` for all of them in one call, and before it had that view answered `mt_balance_of` for one.

Three kinds of token are read, and no contract is typed here:
- wNEAR, the registry's wrapped NEAR. One wNEAR is one NEAR.
- The dollar tokens: every NEAR token the newest 1Click token list prices within 2% of one dollar.
- The pool's other main assets: every NEAR token the list names with the symbol of an asset that holds at least 1% of
  the pool's value on the newest day of NEAR's dashboard series, as the newest reading on file gives it, and that
  registry/token_prices.csv lists with a price. One asset can be several tokens, one for each chain it is bridged
  from, and all the list names are read.
A token is read whether or not the pool holds any today, so one it has emptied still shows what it held. A token that
has left the list, an asset that is under 1% of the pool today and an asset the price registry does not list are not
read at all: this is a history of named
tokens and never the whole pool.

Each balance is read at the first block of the next UTC day, which closes the day. The calls carry a generic client
name and no key, wait several seconds between each other, and stop for the run once the host refuses one twice.
"""
from __future__ import annotations

import gzip
import json
import re
import time
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from ..http import HttpError
from ..pipeline import Context, Skip, dataset, log
from ..settings import BRONZE, read_registry
from .rpc import ARCHIVAL, VIEW_ABSENT, VIEW_FAILED, _view_params

SOURCE = "rpc"
DATASET = "intents_pool_history"
POOL = "intents.near"
# intents.near had its contract at the first block of 2024-12-01 and did not exist at the first block of 2024-11-01
# (view_account at both blocks, read on 2026-11-13), so November 2024 is the first month the pool closed.
FIRST_MONTH_END = date(2024, 11, 30)
DOLLAR_BAND = 0.02  # a token the list prices further than this from one dollar is not counted as a dollar
POOL_SHARES_QUERY = 7586763  # "TVL by asset per day" in registry/dune_queries.csv, which fct_dune_intents_tvl_asset_daily reads
POOL_ASSET_SHARE = 0.01  # an asset with at least this share of the pool's value on the dashboard's newest day is read
POOL_DAYS_PER_RUN = 8  # up to half an hour of archival calls at this job's pace: about 60 calls for a day with every token to read
POOL_FAILURES_PER_RUN = 3
# On 2026-11-13 the archival host answered about 270 calls at its usual pace of one every 1.5 s and then returned HTTP 429
# on most. So this job waits longer before every call, and a call that is still refused after one wait ends the run.
POOL_PAUSE_SECONDS = 4.0
POOL_TRIES_PER_CALL = 2
CLIENT = {"User-Agent": "python-requests"}  # names no person and no project
NOTE = ("assembled: intents.near's balance of wNEAR, of each dollar token and of each token of the pool's other main assets at the first "
        "block of the next UTC day, read from the token contracts with ft_balance_of, and for balances inside a multi-token contract "
        "with mt_batch_balance_of or mt_balance_of; result bytes decoded to JSON; symbol and decimals as the registry and the 1Click "
        "token list gave them on the day of the read; tokens added to the list of those read are added to a day's file")
_NEP141 = re.compile(r"^(?:1cs_v1:near:)?nep141:(.+)$")
_NEP245 = re.compile(r"^nep245:([^:]+):(.+)$")
_AMOUNT = re.compile(r"^\d+$")
_REPLACED = re.compile(r"_?\(deprecated\)$", re.IGNORECASE)  # 1Click's mark on a token it has replaced, as stg_oneclick__tokens reads it


def closing_days(today: date) -> List[date]:
    """The day before the snapshot, then the last day of each complete month back to the pool's first, newest first."""
    days = [today - timedelta(days=1)]
    month_end = today.replace(day=1) - timedelta(days=1)
    while month_end >= FIRST_MONTH_END:
        if month_end not in days:
            days.append(month_end)
        month_end = month_end.replace(day=1) - timedelta(days=1)
    return days


def _newest(pattern: str, snapshot: str) -> List[Any]:
    """The files of a dataset in the newest snapshot folder that the run may see, decoded."""
    paths = sorted(p for p in BRONZE.glob(pattern) if p.parent.name <= f"dt={snapshot}")
    return [json.loads(gzip.decompress(p.read_bytes())) for p in paths if p.parent == paths[-1].parent]


def dashboard_assets(snapshot: str) -> Set[str]:
    """Symbols with at least 1% of the pool's value on the newest day of NEAR's dashboard series, spelled as it spells them.

    The dashboard is read in a browser on request. With no reading on file there is no such list, and only wNEAR and
    the dollar tokens are read.
    """
    rows: List[Dict[str, Any]] = []
    for doc in _newest(f"dune_public/query_results/dt=*/{POOL_SHARES_QUERY}__*.json.gz", snapshot):
        result = (doc or {}).get("execution_succeeded") or {}
        data = result.get("data") or []
        if len(data) >= (result.get("total_row_count") or 0):  # a tile's one-row call is not the series
            rows.extend(r for r in data if r.get("date_at") and r.get("symbol") and type(r.get("tvl_usd")) in (int, float))
    if not rows:
        return set()
    newest = max(str(r["date_at"])[:10] for r in rows)
    value = {r["symbol"]: r["tvl_usd"] for r in rows if str(r["date_at"])[:10] == newest}
    total = sum(value.values())
    return {symbol for symbol, usd in value.items() if total > 0 and usd / total >= POOL_ASSET_SHARE}


def priced_assets() -> Set[str]:
    """Symbols registry/token_prices.csv lists with a source: a main asset is read only when it can be valued."""
    return {r["symbol"] for r in read_registry("token_prices") if r.get("price_source")}


def pool_tokens(snapshot: str) -> List[Dict[str, Any]]:
    """wNEAR, the dollar tokens and the tokens of the pool's other main assets, each with the symbol and decimals its list gives it."""
    lists = _newest("oneclick/tokens/dt=*/all.json.gz", snapshot)
    if not lists:
        raise Skip("run oneclick/tokens first")
    assets = dashboard_assets(snapshot) & priced_assets()
    tokens: Dict[str, Dict[str, Any]] = {}
    for t in read_registry("tokens"):
        if t["token_class"] == "native_wrapped":
            tokens[f"nep141:{t['token_id']}"] = {"asset_id": f"nep141:{t['token_id']}", "standard": "nep141", "contract": t["token_id"],
                                                 "chosen_as": "wrapped_near", "listed_symbol": t["symbol"], "decimals": int(t["decimals"])}
    for t in lists[-1]:
        asset, price, decimals = str(t.get("assetId") or ""), t.get("price"), t.get("decimals")
        ft, mt = _NEP141.match(asset), _NEP245.match(asset)
        if type(decimals) is not int or not isinstance(t.get("symbol"), str) or not (ft or mt):
            continue
        token = ({"asset_id": f"nep141:{ft.group(1)}", "standard": "nep141", "contract": ft.group(1)} if ft else
                 {"asset_id": asset, "standard": "nep245", "contract": mt.group(1), "token_id": mt.group(2)})
        if type(price) in (int, float) and abs(price - 1) <= DOLLAR_BAND:
            chosen = {"chosen_as": "dollar_token", "listed_symbol": t["symbol"], "decimals": decimals, "listed_price": price}
        elif _REPLACED.sub("", t["symbol"]) in assets:
            chosen = {"chosen_as": "other_asset", "listed_symbol": t["symbol"], "decimals": decimals}
        else:
            continue
        tokens.setdefault(token["asset_id"], {**token, **chosen})
    order = {"wrapped_near": 0, "dollar_token": 1, "other_asset": 2}
    return sorted(tokens.values(), key=lambda t: (order[t["chosen_as"]], t["standard"], t["contract"], t.get("token_id", "")))


def _ask(ctx: Context, contract: str, method: str, args: Dict[str, Any], height: int) -> Tuple[Any, Optional[str]]:
    """One view at a past block: (result, None), or (None, the chain's own reason there is none).

    A contract that did not exist yet, or a call that ran and failed, is an answer. Anything else (a node without that
    block, a timeout) raises, so the day is not saved and is read again on a later run.
    """
    request = {"jsonrpc": "2.0", "id": "1", "method": "query", "params": _view_params(contract, method, args, height)}
    time.sleep(POOL_PAUSE_SECONDS)
    reply = ctx.http.post(ARCHIVAL, request, ok=(200, 422), headers=CLIENT, retries=POOL_TRIES_PER_CALL).json()
    result = reply.get("result") or {}
    if "result" in result:
        return json.loads(bytes(result["result"]).decode() or "null"), None
    if result.get("error"):
        return None, VIEW_FAILED
    cause = ((reply.get("error") or {}).get("cause") or {}).get("name")
    if cause in VIEW_ABSENT or cause == VIEW_FAILED:
        return None, cause
    raise RuntimeError(f"{contract}.{method} at block {height}: {cause or 'no result and no cause'}")


def _amounts(values: Any, expected: int, what: str) -> List[str]:
    """Balances arrive as text, so every digit is kept. Anything else is not a balance."""
    if not isinstance(values, list) or len(values) != expected or not all(isinstance(v, str) and _AMOUNT.match(v) for v in values):
        raise RuntimeError(f"{what}: the reply is not {expected} balances")
    return values


def read_pool(ctx: Context, tokens: List[Dict[str, Any]], height: int) -> List[Dict[str, Any]]:
    """Every token's balance at one block: one call per NEP-141 contract, one per NEP-245 contract for all its tokens,
    or one per token where that contract has no view for all of them."""
    rows: List[Dict[str, Any]] = []
    for t in (t for t in tokens if t["standard"] == "nep141"):
        value, error = _ask(ctx, t["contract"], "ft_balance_of", {"account_id": POOL}, height)
        rows.append({**t, "balance": None, "error": error} if error else
                    {**t, "balance": _amounts([value], 1, t["contract"])[0]})
    for contract in sorted({t["contract"] for t in tokens if t["standard"] == "nep245"}):
        group = [t for t in tokens if t["standard"] == "nep245" and t["contract"] == contract]
        value, error = _ask(ctx, contract, "mt_batch_balance_of", {"account_id": POOL, "token_ids": [t["token_id"] for t in group]}, height)
        if error == VIEW_FAILED:
            # v2_1.omni.hot.tg had no batch view at the month ends of April and May 2025, and answered token by token.
            for t in group:
                value, error = _ask(ctx, contract, "mt_balance_of", {"account_id": POOL, "token_id": t["token_id"]}, height)
                rows.append({**t, "balance": None, "error": error} if error else
                            {**t, "balance": _amounts([value], 1, f"{contract} {t['token_id']}")[0]})
            continue
        balances = [None] * len(group) if error else _amounts(value, len(group), contract)
        rows.extend({**t, "balance": b, "error": error} if error else {**t, "balance": b} for t, b in zip(group, balances))
    return rows


@dataset(SOURCE, DATASET, profile="backfill")
def intents_pool_history(ctx: Context) -> None:
    """The named tokens in intents.near on the day before the snapshot and at each month end, newest first.

    One file per day closed and snapshot. Bronze is the record of which tokens a day has an answer for, so a token
    that joins the list later is read at every day already on file, and nothing is asked twice. A contract found
    absent on two newer days is not asked about on older ones.
    """
    heights: Dict[str, int] = {}
    for path in sorted(BRONZE.glob("rpc/block_day/dt=*/*.json.gz")):
        for row in json.loads(gzip.decompress(path.read_bytes())):
            heights[row["day"]] = row["height"]
    if not heights:
        raise Skip("run rpc/block_day first")
    tokens = pool_tokens(ctx.snapshot)
    answered: Dict[str, Set[str]] = {}
    absent: Dict[str, Set[str]] = {}
    for path in BRONZE.glob(f"{SOURCE}/{DATASET}/dt=*/*.json.gz"):
        doc = json.loads(gzip.decompress(path.read_bytes()))
        answered.setdefault(doc["closes_day"], set()).update(b["asset_id"] for b in doc["balances"])
        for contract in {b["contract"] for b in doc["balances"] if b.get("error") in VIEW_ABSENT}:
            absent.setdefault(contract, set()).add(doc["closes_day"])

    def to_ask(day: str) -> List[Dict[str, Any]]:
        gone = {contract for contract, days in absent.items() if sum(1 for d in days if d > day) >= 2}
        return [t for t in tokens if t["asset_id"] not in answered.get(day, ()) and t["contract"] not in gone]

    failures = read = 0
    todo = [d.isoformat() for d in closing_days(date.fromisoformat(ctx.snapshot)) if to_ask(d.isoformat())]
    for day in todo:
        asked = to_ask(day)  # a contract found absent earlier in this run needs no ask on an older day
        if not asked:
            continue
        if read >= POOL_DAYS_PER_RUN:
            break
        block_day = (date.fromisoformat(day) + timedelta(days=1)).isoformat()
        if block_day not in heights:
            ctx.warn(f"{day}: no block height known yet for {block_day}")
            continue
        try:
            balances = read_pool(ctx, asked, heights[block_day])
        except HttpError as e:  # the endpoint refused, or every retry failed: stop asking and leave the rest for another run
            ctx.warn(f"{day}: {e}; stopped, the days still to read wait for a later run")
            break
        except RuntimeError as e:
            ctx.warn(f"{day}: {e}")
            failures += 1
            if failures >= POOL_FAILURES_PER_RUN:
                break
            continue
        for contract in {b["contract"] for b in balances if b.get("error") in VIEW_ABSENT}:
            absent.setdefault(contract, set()).add(day)
        answered.setdefault(day, set()).update(b["asset_id"] for b in balances)
        # A run on the same snapshot day adds to that day's file and does not replace what an earlier run saved there.
        earlier = BRONZE / SOURCE / DATASET / f"dt={ctx.snapshot}" / f"{day}.json.gz"
        kept = json.loads(gzip.decompress(earlier.read_bytes()))["balances"] if earlier.exists() else []
        balances = [b for b in kept if b["asset_id"] not in {n["asset_id"] for n in balances}] + balances
        ctx.bronze.save_json(SOURCE, DATASET, day, {"closes_day": day, "block_day": block_day, "block_height": heights[block_day],
                                                    "account_id": POOL, "balances": balances},
                             url=ARCHIVAL, method="POST", rows=len(balances), params={"block_id": heights[block_day], "account_id": POOL},
                             note=NOTE)
        ctx.bronze.flush()
        read += 1
    left = sum(1 for day in todo if to_ask(day))
    log(f"  {SOURCE}/{DATASET}: {read} days read, {left} still to read")
