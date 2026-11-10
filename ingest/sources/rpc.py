"""NEAR RPC, the on-chain source of truth: protocol config, validators, contract state,
one block per UTC day from the archival node (supply, gas price, epoch, protocol version),
and each held token's own metadata.

`validators` responses are trimmed: per-shard arrays and public keys are dropped, which takes
an epoch from about 400 KB to about 100 KB. Contract view results arrive as a byte array and
are decoded to JSON before saving. Both changes are recorded in the manifest note.
"""
from __future__ import annotations

import base64
import gzip
import json
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ..http import HttpError
from ..pipeline import Context, Skip, dataset, log
from ..settings import BRONZE, read_registry, secret
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
VALIDATOR_ASKS_PER_EPOCH = 24  # the archival host's nodes do not all hold the same epochs, so one refusal settles nothing
EPOCH_LENGTH_BLOCKS = 43200  # the protocol config's epoch_length; an epoch read with fewer blocks counted is still in progress
FT_METADATA_CALLS_PER_RUN = 2000  # about 5 minutes at the keyed pace, and about 8,000 tokens take 4 nights
FT_METADATA_MINUTES_PER_RUN = 40  # a node that rate-limits every call must not stretch the night past the job's timeout
FT_METADATA_SAVE_EVERY = 200
FT_METADATA_FAILURES_IN_A_ROW = 3  # by then the node is the likely problem, so the rest waits for the next run
# These say something about the token, so they are kept. Any other error says something about the node, so the token is asked again.
FT_METADATA_FINAL_ERRORS = {"UNKNOWN_ACCOUNT", "INVALID_ACCOUNT", "NO_CONTRACT_CODE", "CONTRACT_EXECUTION_ERROR"}
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
    ("lst.rhealab.near", "get_total_staked_balance", {}),
    ("sputnik-dao.near", "get_number_daos", {}),
    ("venear.dao", "get_config", {}),
    ("venear.dao", "ft_total_supply", {}),
    ("venear.dao", "get_num_accounts", {}),
    ("wrap.near", "ft_total_supply", {}),
]

# The views replayed at the first block of each past day, so that liquid staking, veNEAR and the Chain Signatures contract
# have a history and not only the nights a snapshot ran. Each is also in VIEW_CALLS.
VIEW_HISTORY_CALLS: List[Tuple[str, str, Dict[str, Any]]] = [
    ("linear-protocol.near", "ft_price", {}),
    ("linear-protocol.near", "ft_total_supply", {}),
    ("linear-protocol.near", "get_total_staked_balance", {}),
    ("meta-pool.near", "get_contract_state", {}),
    ("lst.rhealab.near", "ft_price", {}),
    ("lst.rhealab.near", "ft_total_supply", {}),
    ("lst.rhealab.near", "get_total_staked_balance", {}),
    ("venear.dao", "ft_total_supply", {}),
    ("venear.dao", "get_num_accounts", {}),
    ("v1.signer", "state", {}),
]
VIEW_HISTORY_DAYS_PER_RUN = 60  # about 15 minutes of archival calls at the keyless pace
VIEW_ABSENT = ("UNKNOWN_ACCOUNT", "NO_CONTRACT_CODE")  # the chain's own answer that a contract was not there yet
VIEW_FAILED = "CONTRACT_EXECUTION_ERROR"  # the call ran and failed, as it would on any node

VALIDATOR_KEEP = ("account_id", "stake", "is_slashed", "num_produced_blocks", "num_expected_blocks",
                  "num_produced_chunks", "num_expected_chunks", "num_produced_endorsements", "num_expected_endorsements")


def body(method: str, params: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": "near-thesis", "method": method, "params": params}


def _headers() -> Optional[Dict[str, str]]:
    key = secret("FASTNEAR_API_KEY")
    return {"Authorization": f"Bearer {key}"} if key else None


def _result(ctx: Context, url: str, method: str, params: Any, fresh_connection: bool = False) -> Optional[Any]:
    """Call and return `result`. An RPC-level error, which can arrive as HTTP 200 or 422, returns None.

    A kept-alive connection stays with one of the host's nodes. `fresh_connection` closes it after the call, so the
    next call can reach another node.
    """
    headers = dict(_headers() or {})
    if fresh_connection:
        headers["Connection"] = "close"
    payload = ctx.http.post(url, body(method, params), ok=(200, 422), headers=headers or None).json()
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


def _view_params(contract: str, method: str, args: Dict[str, Any], block_id: Optional[int] = None) -> Dict[str, Any]:
    params = {"request_type": "call_function", "account_id": contract, "method_name": method,
              "args_base64": base64.b64encode(json.dumps(args).encode()).decode()}
    params.update({"block_id": block_id} if block_id else {"finality": "final"})
    return params


def _view(ctx: Context, contract: str, method: str, args: Dict[str, Any], block_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Call a contract view and decode its result. Returns None if the method does not exist or fails."""
    params = _view_params(contract, method, args, block_id)
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
            payload = ctx.http.post(RPC, body("query", params), headers=_headers()).json()
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


def _view_at(ctx: Context, contract: str, method: str, args: Dict[str, Any], height: int) -> Dict[str, Any]:
    """One contract view at a past block: its decoded result, or the chain's own reason there is none.

    A contract that did not exist yet, or a call that ran and failed, is an answer and is kept as `error`. Anything
    else (a node without that block, a timeout) raises, so the day is not saved and is read again on a later run.
    """
    reply = ctx.http.post(ARCHIVAL, body("query", _view_params(contract, method, args, height)), ok=(200, 422), headers=_headers()).json()
    read = {"contract": contract, "method": method, "args": args}
    result = reply.get("result") or {}
    if "result" in result:
        return {**read, "result": json.loads(bytes(result["result"]).decode() or "null")}
    if result.get("error"):
        return {**read, "result": None, "error": VIEW_FAILED, "detail": str(result["error"])[:200]}
    cause = ((reply.get("error") or {}).get("cause") or {}).get("name")
    if cause in VIEW_ABSENT or cause == VIEW_FAILED:
        return {**read, "result": None, "error": cause}
    raise RuntimeError(f"{contract}.{method} at block {height}: {cause or 'no result and no cause'}")


@dataset(SOURCE, "contract_views_history", profile="backfill")
def contract_views_history(ctx: Context) -> None:
    """VIEW_HISTORY_CALLS at the first block of each day that rpc/block_day knows, newest first, a batch per run.

    One file per day. Bronze is the record of which days are done, so a run on another machine is not repeated.
    A contract found absent on two newer days is not asked about on older ones.
    """
    heights: Dict[str, int] = {}
    for path in sorted(BRONZE.glob("rpc/block_day/dt=*/*.json.gz")):
        for row in json.loads(gzip.decompress(path.read_bytes())):
            heights[row["day"]] = row["height"]
    if not heights:
        raise Skip("run rpc/block_day first")
    absent: Dict[str, List[str]] = {}
    done = set()
    for path in BRONZE.glob("rpc/contract_views_history/dt=*/*.json.gz"):
        doc = json.loads(gzip.decompress(path.read_bytes()))
        done.add(doc["day"])
        for contract in {v["contract"] for v in doc["views"] if v.get("error") in VIEW_ABSENT}:
            absent.setdefault(contract, []).append(doc["day"])
    failures = 0
    for day in [d for d in sorted(heights, reverse=True) if d not in done][:VIEW_HISTORY_DAYS_PER_RUN]:
        gone = {contract for contract, days in absent.items() if sum(1 for d in days if d > day) >= 2}
        try:
            views = [_view_at(ctx, contract, method, args, heights[day])
                     for contract, method, args in VIEW_HISTORY_CALLS if contract not in gone]
        except HttpError as e:
            ctx.warn(f"{day}: {e}")
            break
        except RuntimeError as e:
            ctx.warn(f"{day}: {e}")
            failures += 1
            if failures >= 5:
                break
            continue
        for contract in {v["contract"] for v in views if v.get("error") in VIEW_ABSENT}:
            absent.setdefault(contract, []).append(day)
        ctx.bronze.save_json(SOURCE, "contract_views_history", day, {"day": day, "block_height": heights[day], "views": views},
                             url=ARCHIVAL, method="POST", params={"block_id": heights[day], "views": len(views)}, rows=len(views),
                             note="assembled: contract views replayed at the first block of this UTC day; result bytes decoded to JSON")
        ctx.bronze.flush()


def _epoch_is_finished(result: Dict[str, Any]) -> bool:
    """Every block has one expected producer, so a finished epoch's expected blocks add up to its length."""
    return sum(v.get("num_expected_blocks") or 0 for v in result.get("current_validators", [])) >= EPOCH_LENGTH_BLOCKS


def _nightly_epochs_to_read_again(ctx: Context, skip: set) -> List[Tuple[str, str]]:
    """Epochs the nightly read caught in progress, as (epoch_id, day), newest first.

    `validators_current` reads whichever epoch is running, so its block, chunk and endorsement counts stop where the
    read happened. Once a later night shows a newer epoch, the earlier one has ended and can be read whole by its id,
    which the first block of the epoch carries. An epoch already read whole has an `epoch_<height>` file.
    """
    seen: Dict[int, Tuple[int, str]] = {}
    for path in sorted(BRONZE.glob("rpc/validators_current/dt=*/*.json.gz")):
        doc = json.loads(gzip.decompress(path.read_bytes()))
        if doc.get("epoch_height") and doc.get("epoch_start_height"):
            seen.setdefault(int(doc["epoch_height"]), (int(doc["epoch_start_height"]), path.parent.name[len("dt="):]))
    have = {path.name.split(".")[0][len("epoch_"):] for path in BRONZE.glob("rpc/validators_epoch/dt=*/epoch_*.json.gz")}
    newest = max(seen, default=None)
    found = []
    for height in sorted(seen, reverse=True)[:VALIDATOR_EPOCHS_PER_RUN + 1]:
        if height == newest or str(height) in have:
            continue
        start_height, day = seen[height]
        block = _result(ctx, ARCHIVAL, "block", {"block_id": start_height})
        epoch_id = ((block or {}).get("header") or {}).get("epoch_id")
        if epoch_id and epoch_id not in skip:
            found.append((epoch_id, day))
    return found


def _epochs_on_file() -> set:
    """The ids of the epochs already read whole. Bronze is the record: a run elsewhere may have added files this
    checkout's saved state knows nothing about."""
    return {json.loads(gzip.decompress(path.read_bytes())).get("epoch_id")
            for path in BRONZE.glob("rpc/validators_epoch/dt=*/epoch_*.json.gz")}


@dataset(SOURCE, "validators_epoch", profile="backfill")
def validators_epoch(ctx: Context) -> None:
    """Validator set per finished epoch, newest first, a batch per run.

    Two kinds of epoch are read: the one running at 00:00 UTC of each day, and the one each nightly read caught in
    progress. An epoch that has not ended yet is left for a later run and nothing is saved, so every file here holds
    final counts.

    The archival host answers from several nodes, and they do not hold the same epochs. A kept-alive connection stays
    with one node, which is how 316 of 688 epochs came to be refused. Asked again on 2026-11-10, each time on a fresh
    connection, all 316 answered: 291 within 8 asks, the last within 16. So a refused epoch is asked again on later
    runs until it answers or has been refused VALIDATOR_ASKS_PER_EPOCH times.
    """
    state = ctx.load_state("rpc__validators_epoch", {"done": [], "refused": {}})
    refused: Dict[str, int] = state.setdefault("refused", {})
    for epoch_id in state.pop("unavailable", []):  # an earlier version gave up after one refusal
        refused.setdefault(epoch_id, 1)
    epochs: Dict[str, str] = {}
    for path in sorted(BRONZE.glob("rpc/block_day/dt=*/*.json.gz")):
        for row in json.loads(gzip.decompress(path.read_bytes())):
            epochs.setdefault(row["epoch_id"], row["day"])
    done = set(state["done"]) | _epochs_on_file()
    skip = done | {e for e, asks in refused.items() if asks >= VALIDATOR_ASKS_PER_EPOCH}
    wanted = [(e, d) for e, d in sorted(epochs.items(), key=lambda kv: kv[1], reverse=True) if e not in skip and d >= "2025-01-01"]
    todo = [(e, d) for e, d in wanted if e not in refused]
    again = sorted(((e, d) for e, d in wanted if e in refused), key=lambda ed: refused[ed[0]])  # fewest asks first, then newest
    nightly = [(e, d) for e, d in _nightly_epochs_to_read_again(ctx, skip) if e not in epochs]
    for epoch_id, day in (nightly + todo + again)[:VALIDATOR_EPOCHS_PER_RUN]:
        result = _result(ctx, ARCHIVAL, "validators", {"epoch_id": epoch_id}, fresh_connection=True)
        if result is None:
            refused[epoch_id] = refused.get(epoch_id, 0) + 1
            ctx.save_state("rpc__validators_epoch", state)
            continue
        if not _epoch_is_finished(result):
            continue
        ctx.bronze.save_json(SOURCE, "validators_epoch", f"epoch_{result.get('epoch_height')}",
                             {"epoch_id": epoch_id, "seen_on_day": day, **_trim_validators(result)}, url=ARCHIVAL, method="POST",
                             params={"body": body("validators", {"epoch_id": epoch_id})},
                             rows=len(result.get("current_validators", [])),
                             note="trimmed: per-shard arrays and public keys dropped")
        ctx.bronze.flush()
        state["done"].append(epoch_id)
        refused.pop(epoch_id, None)
        ctx.save_state("rpc__validators_epoch", state)


def _bronze_docs(pattern: str) -> Iterator[Any]:
    for path in BRONZE.glob(pattern):
        yield json.loads(gzip.decompress(path.read_bytes()))


def _tokens_seen() -> Counter:
    """Token ids in holdings or top holders, with how many bronze rows each has. Gold drops zero and empty balances, so they don't count."""
    seen: Counter = Counter()
    for doc in _bronze_docs("fastnear/account_full/dt=*/*.json.gz"):
        for token in doc.get("tokens") or []:
            balance = str(token.get("balance") or "")
            if balance.isdigit() and int(balance) > 0:
                seen[token["contract_id"]] += 1
    for doc in _bronze_docs("fastnear/ft_top_holders/dt=*/*.json.gz"):
        if doc.get("token_id"):
            seen[doc["token_id"]] += len(doc.get("accounts") or [])
    return seen


def _ft_text(value: Any, limit: int) -> Optional[str]:
    """A contract can put anything in these fields, so keep printable characters only, up to a limit."""
    if not isinstance(value, str):
        return None
    return "".join(c for c in value if c.isprintable()).strip()[:limit] or None


def _ft_metadata_row(ctx: Context, token: str) -> Dict[str, Any]:
    """What one token's contract says through ft_metadata. Raises if the node gave no answer about the token."""
    payload = ctx.http.post(RPC, body("query", _view_params(token, "ft_metadata", {})), ok=(200, 422), headers=_headers()).json()
    cause = (payload.get("error") or {}).get("cause") or {}
    if cause.get("name") in FT_METADATA_FINAL_ERRORS:
        return {"token_id": token, "block_height": (cause.get("info") or {}).get("block_height"), "error": cause["name"]}
    result = payload.get("result")
    if not isinstance(result, dict) or not ("result" in result or "error" in result):
        raise ValueError(f"no answer about the token: {cause.get('name') or 'empty reply'}")
    row = {"token_id": token, "block_height": result.get("block_height")}
    if "result" not in result:  # the contract has no such method, or it panicked
        return {**row, "error": "CONTRACT_EXECUTION_ERROR"}
    try:
        metadata = json.loads(bytes(result["result"]).decode())
    except (TypeError, ValueError, RecursionError):  # anyone can deploy a token, so its reply can be built to break a parser
        metadata = None
    if not isinstance(metadata, dict):
        return {**row, "error": "NOT_METADATA"}
    row.update(spec=_ft_text(metadata.get("spec"), 32), name=_ft_text(metadata.get("name"), 128), symbol=_ft_text(metadata.get("symbol"), 64))
    decimals = metadata.get("decimals")
    if type(decimals) is int and 0 <= decimals <= 255:  # a u8 in the standard, NEP-148; `type` because True is an int to isinstance
        return {**row, "decimals": decimals}
    return {**row, "error": "BAD_DECIMALS"}


def _flush_ft_metadata(ctx: Context, rows: List[Dict[str, Any]], state: Dict[str, Any]) -> None:
    if rows:
        ctx.bronze.save_json(SOURCE, "ft_metadata", f"from_{rows[0]['token_id']}", rows, url=RPC, method="POST", rows=len(rows),
                             params={"view": "ft_metadata"},
                             note="assembled: one ft_metadata view per token, read once; icon and reference dropped, spec, name and symbol "
                                  "cut to printable characters and 32, 128 and 64 characters")
        ctx.bronze.flush()
    ctx.save_state("rpc__ft_metadata", state)


@dataset(SOURCE, "ft_metadata")
def ft_metadata(ctx: Context) -> None:
    """Decimals and symbol from each token seen in holdings or top holders, read once, most rows first, a batch per run.

    `answers` in the state file keeps every answer, including "this contract has no metadata". A token with no answer about it
    is asked again on a later run, after the tokens that have not failed yet, so it cannot hold up the queue. Bronze holds one
    file per run, named after the run's first token.
    """
    state = ctx.load_state("rpc__ft_metadata", {"answers": {}, "failures": {}})
    answers, failures = state["answers"], state["failures"]
    # The nightly job drops its own bronze dated up to main's pin, and a run on the pin's day writes there. An answer without its file is read again.
    on_file = {row["token_id"] for doc in _bronze_docs("rpc/ft_metadata/dt=*/*.json.gz") for row in doc}
    seen = _tokens_seen()
    todo = sorted((t for t in seen if t not in answers or t not in on_file), key=lambda t: (failures.get(t, 0), -seen[t], t))
    rows: List[Dict[str, Any]] = []
    in_a_row = 0
    deadline = time.monotonic() + FT_METADATA_MINUTES_PER_RUN * 60
    try:
        for token in todo[:FT_METADATA_CALLS_PER_RUN]:
            if time.monotonic() > deadline:
                ctx.warn(f"stopped after {FT_METADATA_MINUTES_PER_RUN} minutes; the remaining tokens wait for the next run")
                break
            try:
                row = _ft_metadata_row(ctx, token)
            except (HttpError, ValueError, AttributeError) as e:  # AttributeError: a reply that is not shaped like JSON-RPC
                ctx.warn(f"{token}: {e}")
                failures[token] = failures.get(token, 0) + 1
                in_a_row += 1
                # Status 0 means every retry failed, which has already taken about 15 minutes.
                if in_a_row >= FT_METADATA_FAILURES_IN_A_ROW or getattr(e, "status", None) == 0:
                    ctx.warn("stopped early; the remaining tokens wait for the next run")
                    break
                continue
            in_a_row = 0
            failures.pop(token, None)
            rows.append(row)
            answers[token] = {k: row[k] for k in ("decimals", "symbol", "error") if row.get(k) is not None}
            if len(rows) % FT_METADATA_SAVE_EVERY == 0:
                _flush_ft_metadata(ctx, rows, state)
    finally:
        _flush_ft_metadata(ctx, rows, state)
    log(f"  rpc/ft_metadata: {len(rows)} tokens read, {len(todo) - len(rows)} still to read")
