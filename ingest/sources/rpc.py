"""NEAR RPC, the on-chain source of truth: protocol config, validators, contract state,
and one block per UTC day from the archival node (supply, gas price, epoch, protocol version).

`validators` responses are trimmed: per-shard arrays and public keys are dropped, which takes
an epoch from about 400 KB to about 100 KB. Contract view results arrive as a byte array and
are decoded to JSON before saving. Both changes are recorded in the manifest note.
"""
from __future__ import annotations

import base64
import gzip
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ..http import HttpError
from ..pipeline import Context, Skip, dataset
from ..settings import BRONZE, read_registry
from ._common import fetch

SOURCE = "rpc"
RPC = "https://free.rpc.fastnear.com"
ARCHIVAL = "https://archival-rpc.mainnet.fastnear.com"
GENESIS_HEIGHT = 9820210
DAILY_FROM = date(2025, 1, 1)
MONTHLY_FROM = date(2020, 8, 1)
TOLERANCE_NS = 120 * 10**9
NS_PER_S = 10**9
BLOCK_DAYS_PER_RUN = 400  # keyless archival calls are slow, so a long backfill spreads over several runs
RECENT_DAYS = 14
VALIDATOR_EPOCHS_PER_RUN = 40
FEE_COLLECTOR = "7066024d3f20f94de601c003163367873cca78507eeca4df66d9be645f197f05"

# (contract, method, args). Each result is decoded and saved as one file per night.
VIEW_CALLS: List[Tuple[str, str, Dict[str, Any]]] = [
    ("v1.signer", "state", {}),
    ("v1.signer", "version", {}),
    ("intents.near", "fee", {}),
    ("intents.near", "fee_collector", {}),
    ("intents.near", "mt_tokens_for_owner", {"account_id": FEE_COLLECTOR, "limit": 200}),
    ("linear-protocol.near", "ft_price", {}),
    ("linear-protocol.near", "ft_total_supply", {}),
    ("linear-protocol.near", "get_total_staked_balance", {}),
    ("meta-pool.near", "get_contract_state", {}),
    ("lst.rhealab.near", "ft_price", {}),
    ("lst.rhealab.near", "ft_total_supply", {}),
    ("sputnik-dao.near", "get_number_daos", {}),
    ("venear.dao", "get_config", {}),
    ("venear.dao", "ft_total_supply", {}),
    ("venear.dao", "get_num_accounts", {}),
    ("wrap.near", "ft_total_supply", {}),
]

VALIDATOR_KEEP = ("account_id", "stake", "is_slashed", "num_produced_blocks", "num_expected_blocks",
                  "num_produced_chunks", "num_expected_chunks", "num_produced_endorsements", "num_expected_endorsements")


def body(method: str, params: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": "near-thesis", "method": method, "params": params}


def _result(ctx: Context, url: str, method: str, params: Any) -> Optional[Any]:
    """Call and return `result`. An RPC-level error, which can arrive as HTTP 200 or 422, returns None."""
    payload = ctx.http.post(url, body(method, params), ok=(200, 422)).json()
    return payload.get("result")


def _trim_validators(result: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "epoch_height": result.get("epoch_height"),
        "epoch_start_height": result.get("epoch_start_height"),
        "validators": [{k: v.get(k) for k in VALIDATOR_KEEP} for v in result.get("current_validators", [])],
        "next_validators": [{"account_id": v.get("account_id"), "stake": v.get("stake")} for v in result.get("next_validators", [])],
        "prev_epoch_kickout": result.get("prev_epoch_kickout"),
    }


@dataset(SOURCE, "status")
def status(ctx: Context) -> None:
    fetch(ctx, SOURCE, "status", "all", RPC, method="POST", body=body("status", []))


@dataset(SOURCE, "protocol_config")
def protocol_config(ctx: Context) -> None:
    fetch(ctx, SOURCE, "protocol_config", "final", RPC, method="POST",
          body=body("EXPERIMENTAL_protocol_config", {"finality": "final"}))


@dataset(SOURCE, "gas_price")
def gas_price(ctx: Context) -> None:
    fetch(ctx, SOURCE, "gas_price", "latest", RPC, method="POST", body=body("gas_price", [None]))


@dataset(SOURCE, "validators_current")
def validators_current(ctx: Context) -> None:
    result = _result(ctx, RPC, "validators", [None])
    if result is None:
        raise Skip("validators returned an RPC error")
    ctx.bronze.save_json(SOURCE, "validators_current", "latest", _trim_validators(result), url=RPC, method="POST",
                         params={"body": body("validators", [None])}, rows=len(result.get("current_validators", [])),
                         note="trimmed: per-shard arrays and public keys dropped")


def _view(ctx: Context, contract: str, method: str, args: Dict[str, Any], block_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Call a contract view and decode its result. Returns None if the method does not exist or fails."""
    params = {"request_type": "call_function", "account_id": contract, "method_name": method,
              "args_base64": base64.b64encode(json.dumps(args).encode()).decode()}
    params.update({"block_id": block_id} if block_id else {"finality": "final"})
    try:
        result = _result(ctx, ARCHIVAL if block_id else RPC, "query", params)
    except HttpError as e:
        ctx.warn(f"{contract}.{method}: {e}")
        return None
    if not result or "result" not in result:
        ctx.warn(f"{contract}.{method}: no result (the method may not exist)")
        return None
    return {"block_height": result.get("block_height"), "contract": contract, "method": method, "args": args,
            "result": json.loads(bytes(result["result"]).decode() or "null")}


@dataset(SOURCE, "contract_views")
def contract_views(ctx: Context) -> None:
    for contract, method, args in VIEW_CALLS:
        view = _view(ctx, contract, method, args)
        if view:
            ctx.bronze.save_json(SOURCE, "contract_views", f"{contract}__{method}", view, url=RPC, method="POST",
                                 params={"contract": contract, "view": method, "args": args},
                                 note="result bytes decoded to JSON")


@dataset(SOURCE, "hos_proposals")
def hos_proposals(ctx: Context) -> None:
    """Every House of Stake proposal with its status and votes, read from the voting contract."""
    count = _view(ctx, "vote.dao", "get_num_proposals", {})
    if not count:
        raise Skip("vote.dao get_num_proposals returned nothing")
    rows: List[Any] = []
    for start in range(0, count["result"], 20):
        page = _view(ctx, "vote.dao", "get_proposals", {"from_index": start, "limit": 20})
        rows.extend(page["result"] if page else [])
    ctx.bronze.save_json(SOURCE, "hos_proposals", "vote.dao", rows, url=RPC, method="POST", rows=len(rows),
                         params={"contract": "vote.dao", "view": "get_proposals"},
                         note="assembled from get_proposals pages; result bytes decoded to JSON")


@dataset(SOURCE, "accounts")
def accounts(ctx: Context) -> None:
    """Balance, stake and contract hash for each registry account, as a daily point-in-time record."""
    rows = []
    for e in read_registry("entities"):
        params = {"request_type": "view_account", "finality": "final", "account_id": e["account_id"]}
        try:
            payload = ctx.http.post(RPC, body("query", params)).json()
        except HttpError as err:
            ctx.warn(f"{e['account_id']}: {err}")
            continue
        result = payload.get("result")
        error = (payload.get("error") or {}).get("cause", {}).get("name")
        rows.append({"account_id": e["account_id"], "exists": result is not None, "error": error, **(result or {})})
    ctx.bronze.save_json(SOURCE, "accounts", "registry", rows, url=RPC, method="POST", rows=len(rows),
                         note="assembled: one view_account call per registry account")


def _header(ctx: Context, height: int) -> Optional[Dict[str, Any]]:
    result = _result(ctx, ARCHIVAL, "block", {"block_id": height})
    return result["header"] if result else None


def _existing_header(ctx: Context, height: int, limit: int = 30) -> Dict[str, Any]:
    """Some heights have no block, so walk forward to the next one that exists."""
    for offset in range(limit):
        header = _header(ctx, height + offset)
        if header:
            return header
    raise RuntimeError(f"no block found within {limit} heights after {height}")


def _block_at(ctx: Context, target_ns: int, lo: Dict[str, Any], hi: Dict[str, Any]) -> Dict[str, Any]:
    """Bracket search for a block at or within TOLERANCE_NS after target_ns."""
    for _ in range(60):
        hi_t, lo_t = int(hi["timestamp"]), int(lo["timestamp"])
        if target_ns <= hi_t <= target_ns + TOLERANCE_NS:
            return hi
        span = hi["height"] - lo["height"]
        if span <= 1:
            return hi
        guess = lo["height"] + int((target_ns - lo_t) * span / max(hi_t - lo_t, 1))
        guess = min(max(guess, lo["height"] + 1), hi["height"] - 1)
        header = _existing_header(ctx, guess)
        if header["height"] >= hi["height"]:
            return hi
        if int(header["timestamp"]) >= target_ns:
            hi = header
        else:
            lo = header
    return hi


def _days_wanted(today: date) -> List[date]:
    days, d = [], MONTHLY_FROM
    while d < DAILY_FROM:
        days.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    d = DAILY_FROM
    while d <= today:
        days.append(d)
        d += timedelta(days=1)
    return days


@dataset(SOURCE, "block_day")
def block_day(ctx: Context) -> None:
    """One block per wanted UTC day. Resumable: a state file remembers the heights already found.

    Monthly from 2020-08 and daily from 2025-01. Bronze holds one file per run with the header fields
    the warehouse uses, named after the run's first day; `rows` in the manifest gives the day count.
    """
    known: Dict[str, int] = ctx.load_state("rpc__block_day", {})
    today = date.fromisoformat(ctx.snapshot)
    missing = [d for d in _days_wanted(today) if d.isoformat() not in known]
    if not missing:
        return
    # Recent days come first because the block sampler needs them; older days follow, a batch per run.
    recent = [d for d in missing if d >= today - timedelta(days=RECENT_DAYS)]
    older = [d for d in missing if d < today - timedelta(days=RECENT_DAYS)][:BLOCK_DAYS_PER_RUN]
    tip = _result(ctx, ARCHIVAL, "block", {"finality": "final"})["header"]
    rows: List[Dict[str, Any]] = []
    flush_key = None
    try:
        for batch in (recent, older):
            if not batch:
                continue
            earlier = [h for d, h in known.items() if d < batch[0].isoformat()]
            lo = _existing_header(ctx, max(earlier) if earlier else GENESIS_HEIGHT)
            for i, day in enumerate(batch):
                target = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp()) * NS_PER_S
                # Each batch is ascending, so each find is a good lower bound for the next day.
                header = _block_at(ctx, target, lo, tip)
                lo = header
                known[day.isoformat()] = header["height"]
                rows.append({"day": day.isoformat(), "height": header["height"], "hash": header["hash"],
                             "timestamp": header["timestamp"], "total_supply": header["total_supply"],
                             "gas_price": header["gas_price"], "epoch_id": header["epoch_id"],
                             "protocol_version": header.get("latest_protocol_version")})
                if (i + 1) % 25 == 0:
                    flush_key = _flush_block_days(ctx, rows, known, flush_key)
            flush_key = _flush_block_days(ctx, rows, known, flush_key)
    finally:
        _flush_block_days(ctx, rows, known, flush_key)


def _flush_block_days(ctx: Context, rows: List[Dict[str, Any]], known: Dict[str, int], key: Optional[str]) -> Optional[str]:
    if not rows:
        return key
    key = key or f"from_{rows[0]['day']}"
    ctx.bronze.save_json(SOURCE, "block_day", key, rows, url=ARCHIVAL, method="POST", rows=len(rows),
                         note="assembled: header fields of one block per UTC day, within 120 s after 00:00")
    ctx.bronze.flush()
    ctx.save_state("rpc__block_day", known)
    return key


@dataset(SOURCE, "validators_epoch", profile="backfill")
def validators_epoch(ctx: Context) -> None:
    """Validator set per epoch, newest first, a batch per run. Older epochs may be unavailable from the node."""
    state = ctx.load_state("rpc__validators_epoch", {"done": [], "unavailable": []})
    epochs: Dict[str, str] = {}
    for path in sorted(BRONZE.glob("rpc/block_day/dt=*/*.json.gz")):
        for row in json.loads(gzip.decompress(path.read_bytes())):
            epochs.setdefault(row["epoch_id"], row["day"])
    skip = set(state["done"]) | set(state["unavailable"])
    todo = [(e, d) for e, d in sorted(epochs.items(), key=lambda kv: kv[1], reverse=True) if e not in skip and d >= "2025-01-01"]
    for epoch_id, day in todo[:VALIDATOR_EPOCHS_PER_RUN]:
        result = _result(ctx, ARCHIVAL, "validators", {"epoch_id": epoch_id})
        if result is None:
            state["unavailable"].append(epoch_id)
            ctx.save_state("rpc__validators_epoch", state)
            continue
        ctx.bronze.save_json(SOURCE, "validators_epoch", f"epoch_{result.get('epoch_height')}",
                             {"epoch_id": epoch_id, "seen_on_day": day, **_trim_validators(result)}, url=ARCHIVAL, method="POST",
                             params={"body": body("validators", {"epoch_id": epoch_id})},
                             rows=len(result.get("current_validators", [])),
                             note="trimmed: per-shard arrays and public keys dropped")
        state["done"].append(epoch_id)
        ctx.save_state("rpc__validators_epoch", state)
