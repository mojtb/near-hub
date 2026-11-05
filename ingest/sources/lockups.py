"""NEAR's lockup contracts, read on chain, so gold can build a circulating supply this warehouse can check.

NEAR defines circulating supply as every token not subject to a lockup at that moment. Every lockup is a subaccount of
lockup.near, so that account's transfers list them all, and each contract's stored state holds its schedule. Gold sums
the schedules per day with the formula NEAR Explorer used: see fct_circulating_supply_daily and docs/CIRCULATING_SUPPLY.md.

Owners are people's accounts, so no account name is stored. A lockup is known by its place in the factory's order, which
only grows at the end, and its owner and staking pool are dropped. The list is read again on each run, so a number leads
back to the same account for anyone who repeats the crawl, and the repository holds no list of people's wallets.

A first read takes up to five calls per lockup, and more if vesting was terminated, so a missing history fills in over
several runs. After that, a night reads the list, any new lockup, and the few contracts that can still change.
"""
from __future__ import annotations

import base64
import gzip
import json
import struct
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..pipeline import Context, dataset
from ..settings import BRONZE
from .fastnear import PAGE_SIZE, TRANSFERS
from .fastnear import _headers as _fastnear_headers
from .rpc import ARCHIVAL, RPC, _headers, _header, _view, body

SOURCE = "rpc"
DATASET = "lockups"
FACTORY = "lockup.near"
SUFFIX = ".lockup.near"
# NEAR Explorer subtracted these two accounts' balances as well: lockup.near funds new lockups, and contributors.near held
# 418M NEAR at genesis and has since paid nearly all of it out.
FOUNDATION_LOCKED = (FACTORY, "contributors.near")
FIRST_READS_PER_RUN = 200  # about 15 minutes of archival calls at the keyless pace
STATE_KEY = base64.b64encode(b"STATE").decode()
# After a contract's creation receipt, state is there from the next block that exists. Some heights have no block.
READ_OFFSETS = (2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 300, 600, 1200)
HEIGHT_TRIES = 30
# Days the contracts' own answer is read on, to test the formula in gold. Each has a height in data/state/rpc__block_day.json.
VIEW_CHECK_DAYS = ("2020-12-01", "2021-07-01", "2022-07-01", "2023-07-01", "2024-07-01", "2025-08-01", "2025-10-01", "2025-11-01")
VIEW_SAMPLE_EVERY = 29  # about 185 lockups, chosen by number, so a later run picks the same ones


def parse_state(raw: bytes) -> Dict[str, Any]:
    """Decode the lockup contract's borsh state. Raises ValueError for anything else, such as a contract replaced later.

    Field order is from near/core-contracts lockup/src/lib.rs and types.rs. The owner, whitelist, staking pool and
    foundation account are read to find the next field and never returned.
    """
    position = 0

    def take(size: int) -> bytes:
        nonlocal position
        piece = raw[position:position + size]
        if len(piece) < size:
            raise ValueError("state ends early")
        position += size
        return piece

    def u8() -> int:
        return take(1)[0]

    def u64() -> int:
        return struct.unpack("<Q", take(8))[0]

    def u128() -> int:
        return int.from_bytes(take(16), "little")

    def text() -> str:
        return take(struct.unpack("<I", take(4))[0]).decode()

    def optional_u64() -> Optional[int]:
        flag = u8()
        if flag > 1:
            raise ValueError("bad option flag")
        return u64() if flag else None

    try:
        text()  # owner
        fields: Dict[str, Any] = {"lockup_amount": u128(), "withdrawn": u128(), "lockup_duration_ns": u64(),
                                  "release_duration_ns": optional_u64(), "lockup_timestamp_ns": optional_u64()}
        transfers = u8()
        if transfers == 0:
            u64()
        elif transfers == 1:
            text()
        else:
            raise ValueError("bad transfers tag")
        fields["transfers_enabled"] = transfers == 0
        vesting = u8()
        if vesting == 0:
            fields["vesting_kind"] = "none"
        elif vesting == 1:
            take(struct.unpack("<I", take(4))[0])
            fields["vesting_kind"] = "hash"
        elif vesting == 2:
            fields.update(vesting_kind="schedule", vesting_start_ns=u64(), vesting_cliff_ns=u64(), vesting_end_ns=u64())
        elif vesting == 3:
            fields.update(vesting_kind="terminating", unvested=u128())
            u8()  # termination status
        else:
            raise ValueError("bad vesting tag")
        text()  # staking pool whitelist
        if u8() == 1:  # staking information
            text()
            u8()
            u128()
        if u8() == 1:  # foundation account
            text()
    except (struct.error, UnicodeDecodeError) as e:
        raise ValueError(str(e)) from e
    if position != len(raw):
        raise ValueError("bytes left over")
    return fields


def _read_state(ctx: Context, account: str, height: Optional[int] = None) -> Tuple[str, Optional[Dict[str, Any]]]:
    """A contract's fields at a block, or the tip. Returns a status: ok, no_account, no_block or not_a_lockup."""
    params: Dict[str, Any] = {"request_type": "view_state", "account_id": account, "prefix_base64": STATE_KEY}
    params.update({"block_id": height} if height else {"finality": "final"})
    payload = ctx.http.post(ARCHIVAL if height else RPC, body("query", params), ok=(200, 422), headers=_headers()).json()
    result = payload.get("result") or {}
    cause = ((payload.get("error") or {}).get("cause") or {}).get("name") or ""
    message = str(result.get("error") or (payload.get("error") or {}).get("message") or "")
    if cause == "UNKNOWN_ACCOUNT" or "does not exist" in message:
        return "no_account", None
    if cause == "UNKNOWN_BLOCK":
        return "no_block", None
    values = [v["value"] for v in result.get("values", []) if v.get("key") == STATE_KEY]
    if not values:
        return ("not_a_lockup", None) if "values" in result else ("no_block", None)
    try:
        return "ok", parse_state(base64.b64decode(values[0]))
    except ValueError:
        return "not_a_lockup", None


def _state_at_or_after(ctx: Context, account: str, height: int) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Walk forward past heights that hold no block."""
    status: Tuple[str, Optional[Dict[str, Any]]] = ("no_block", None)
    for offset in range(HEIGHT_TRIES):
        status = _read_state(ctx, account, height + offset)
        if status[0] != "no_block":
            return status
    return status


def _code_hash(ctx: Context, account: str, height: int) -> Optional[str]:
    params = {"request_type": "view_account", "account_id": account, "block_id": height}
    return (ctx.http.post(ARCHIVAL, body("query", params), ok=(200, 422), headers=_headers()).json().get("result") or {}).get("code_hash")


def _transfers(ctx: Context, account: str, **options: Any) -> List[Dict[str, Any]]:
    """Every transfer of one account, oldest first, unless `limit` and `desc` ask for less."""
    rows: List[Dict[str, Any]] = []
    token = None
    while True:
        request = {"account_id": account, "limit": options.get("limit", PAGE_SIZE), "desc": options.get("desc", False)}
        if token:
            request["resume_token"] = token
        payload = ctx.http.post(f"{TRANSFERS}/v0/transfers", request, headers=_fastnear_headers()).json()
        page = payload.get("transfers") or []
        rows.extend(page)
        token = payload.get("resume_token")
        if "limit" in options or not token or len(page) < PAGE_SIZE:
            return rows


def factory_lockups(transfers: List[Dict[str, Any]]) -> List[Tuple[str, int, int]]:
    """(account, height, time) of each lockup in the order they were made, one per funding from the factory, with height and then
    name settling ties. A lockup's name comes from its owner, so an owner can delete one and be given another under the same name."""
    made = set()
    for t in transfers:
        other = t.get("other_account_id") or ""
        if t.get("asset_id") == "native:near" and other.endswith(SUFFIX) and int(t["amount"]) < 0:
            made.add((int(t["block_height"]), other, int(t["block_timestamp"])))
    return [(account, height, ns) for height, account, ns in sorted(made)]


def daily_balances(account: str, transfers: List[Dict[str, Any]], before_day: str) -> List[Dict[str, str]]:
    """The running balance FastNear reports at the end of each day with a native transfer, leaving out the day still under way."""
    last: Dict[str, Tuple[int, str]] = {}
    for t in transfers:
        if t.get("asset_id") != "native:near" or t.get("end_of_block_balance") is None:
            continue
        day = datetime.fromtimestamp(int(t["block_timestamp"]) // 10**9, timezone.utc).strftime("%Y-%m-%d")
        if day < before_day and (day not in last or int(t["block_height"]) >= last[day][0]):
            last[day] = (int(t["block_height"]), t["end_of_block_balance"])
    return [{"account_id": account, "date_day": day, "balance_yocto": balance} for day, (_, balance) in sorted(last.items())]


def schedule_end_ns(row: Dict[str, Any], transfers_enabled_ns: int = 1602614338293769340) -> int:
    """The moment a schedule has fully run out. The contract's own arithmetic can end earlier, never later."""
    start = max(transfers_enabled_ns + int(row["lockup_duration_ns"]), int(row.get("lockup_timestamp_ns") or 0))
    return max(start + int(row.get("release_duration_ns") or 0), int(row.get("vesting_end_ns") or 0))


def _stored(fields: Dict[str, Any]) -> Dict[str, Any]:
    """Big numbers travel as text, so they keep every digit."""
    return {k: (str(v) if isinstance(v, int) and not isinstance(v, bool) else v) for k, v in fields.items()}


def _termination_key(fields: Dict[str, Any]) -> Tuple[str, int, int]:
    return fields["vesting_kind"], int(fields.get("withdrawn") or 0), int(fields.get("unvested") or 0)


def _first_height_where_not(ctx: Context, account: str, low: int, high: int, holds: Callable[[Dict[str, Any]], bool]) -> Optional[Tuple[int, int]]:
    """Search the blocks for where a condition stops holding: true at low, false at high. Returns that height and its block's time."""
    while high - low > 1:
        middle = (low + high) // 2
        status, fields = _state_at_or_after(ctx, account, middle)
        if status == "ok" and holds(fields):
            low = middle
        else:
            high = middle
    for offset in range(HEIGHT_TRIES):
        header = _header(ctx, high + offset)
        if header:
            return high, int(header["timestamp"])
    return None


def _date_termination(ctx: Context, account: str, row: Dict[str, Any], fields: Dict[str, Any], low: int, high: int) -> Dict[str, Any]:
    """When vesting was terminated and when the unvested tokens finished leaving. Between the two, the contract locks them."""
    key = _termination_key(row)
    started = _first_height_where_not(ctx, account, low, high, lambda f: _termination_key(f) == key)
    if started is None:
        return {}
    height, ns = started
    dated: Dict[str, Any] = {"changed_ns": str(ns), "finished_ns": str(ns)}
    if fields["vesting_kind"] == "terminating":  # still open, so the newest state already says what is locked
        return dated
    status, opening = _state_at_or_after(ctx, account, height)
    if status == "ok" and opening["vesting_kind"] == "terminating":
        ended = _first_height_where_not(ctx, account, height, high, lambda f: f["vesting_kind"] == "terminating")
        if ended:
            dated.update(terminating_unvested=str(opening["unvested"]), finished_ns=str(ended[1]))
    return dated


def _first_read(ctx: Context, number: int, account: str, height: int, ns: int) -> Dict[str, Any]:
    row: Dict[str, Any] = {"lockup_no": number, "created_height": height, "created_ns": str(ns)}
    seen = set()
    for offset in READ_OFFSETS:
        status, fields = _read_state(ctx, account, height + offset)
        seen.add(status)
        if status == "ok":
            return {**row, "first_read_height": height + offset, "code_hash": _code_hash(ctx, account, height + offset),
                    **_stored(fields), "status": "live", "changed_ns": None, "gone_ns": None}
    # An account that is not a lockup contract holds nothing locked. If no block answered, a later run tries again.
    return {**row, "status": "unread" if seen == {"no_block"} else "not_a_lockup"}


def _last_move(ctx: Context, account: str, before_height: Optional[int]) -> Optional[Dict[str, Any]]:
    if before_height is None:
        moved = _transfers(ctx, account, limit=1, desc=True)
        return moved[0] if moved else None
    older = [t for t in _transfers(ctx, account) if int(t["block_height"]) < before_height]
    return older[-1] if older else None


def _follow_up(ctx: Context, account: str, row: Dict[str, Any], next_lockup_height: Optional[int] = None) -> Dict[str, Any]:
    """Bring a lockup up to date: gone, replaced, or changed by a termination. Unchanged rows come back as they were.
    If another lockup was later made under this name, the tip describes that one, so this one is read as it was before."""
    status, fields = ("no_account", None) if next_lockup_height else _read_state(ctx, account)
    if status == "no_block":  # the node had a bad moment; the next run tries again
        return row
    updated = dict(row)
    read_height: Optional[int] = None
    if status != "ok":
        when = _last_move(ctx, account, next_lockup_height)
        updated.update(status="deleted" if status == "no_account" else "replaced", gone_ns=when["block_timestamp"] if when else row["created_ns"])
        if when is None or row.get("vesting_kind") not in ("schedule", "hash"):
            return updated
        # A termination leaves no trace once the account is gone, so read just before the last transfer.
        read_height = int(when["block_height"]) - 1
        fields = _last_state_before(ctx, account, read_height, int(row["first_read_height"]))
        if fields is None:
            return updated
    updated["transfers_enabled"] = fields["transfers_enabled"]
    if _termination_key(fields) != _termination_key(row):
        updated.update(_stored({"last_vesting_kind": fields["vesting_kind"], "last_withdrawn": fields["withdrawn"], "last_unvested": fields.get("unvested", 0)}))
        if not row.get("changed_ns"):
            read_height = read_height or _tip_height(ctx)
            low = max(int(row["first_read_height"]), int(row.get("last_read_height") or 0))
            updated.update(_date_termination(ctx, account, row, fields, low, read_height))
        elif row.get("last_vesting_kind") == "terminating" and fields["vesting_kind"] != "terminating":
            read_height = read_height or _tip_height(ctx)
            ended = _first_height_where_not(ctx, account, int(row["last_read_height"]), read_height, lambda f: f["vesting_kind"] == "terminating")
            updated.update(terminating_unvested=row["last_unvested"], finished_ns=str(ended[1]) if ended else row["changed_ns"])
    if updated != row or "last_read_height" not in row:
        updated["last_read_height"] = read_height or _tip_height(ctx)
    return updated


def _last_state_before(ctx: Context, account: str, height: int, floor: int) -> Optional[Dict[str, Any]]:
    """The newest readable state at or below a height, stepping down in growing strides."""
    stride = 0
    while height - stride >= floor:
        status, fields = _read_state(ctx, account, height - stride)
        if status == "ok":
            return fields
        stride = stride * 2 + 1
    return None


def _tip_height(ctx: Context) -> int:
    payload = ctx.http.post(RPC, body("block", {"finality": "final"}), headers=_headers()).json()
    return payload["result"]["header"]["height"]


def known_rows() -> Dict[int, Dict[str, Any]]:
    """The newest stored row per lockup, from every snapshot on disk."""
    rows: Dict[int, Dict[str, Any]] = {}
    for path in sorted(BRONZE.glob(f"{SOURCE}/{DATASET}/dt=*/schedules.json.gz")):
        for row in json.loads(gzip.decompress(path.read_bytes())):
            rows[row["lockup_no"]] = row
    return rows


def _can_still_change(row: Dict[str, Any], now_ns: int) -> bool:
    """Only these can move the supply: a schedule still running, a termination still open, or transfers never turned on."""
    if row.get("status") != "live":
        return False
    open_termination = (row.get("last_vesting_kind") or row.get("vesting_kind")) == "terminating"
    return schedule_end_ns(row) > now_ns or open_termination or row.get("transfers_enabled") is False


def _check_views(ctx: Context, read_day: str, height: int, rows: List[Tuple[str, Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """The contracts' own answer at a block, to hold gold's formula to."""
    header = None
    for offset in range(HEIGHT_TRIES):
        header = _header(ctx, height + offset)
        if header:
            height = header["height"]
            break
    if header is None:
        ctx.warn(f"{read_day}: no block near height {height}")
        return []
    checked: List[Dict[str, Any]] = []
    for account, row in rows:
        locked = _view(ctx, account, "get_locked_amount", {}, block_id=height)
        enabled = _view(ctx, account, "are_transfers_enabled", {}, block_id=height)
        if locked and enabled:
            checked.append({"read_day": read_day, "height": height, "block_ns": str(header["timestamp"]), "lockup_no": row["lockup_no"],
                            "locked_yocto": locked["result"], "transfers_enabled": enabled["result"]})
    return checked


def _existed_on(row: Dict[str, Any], read_day: str, height: int) -> bool:
    if int(row["created_height"]) >= height or "lockup_amount" not in row:
        return False
    gone = row.get("gone_ns")
    return not gone or datetime.fromtimestamp(int(gone) // 10**9, timezone.utc).strftime("%Y-%m-%d") > read_day


def _saved_days(name: str) -> set:
    days = set()
    for path in BRONZE.glob(f"{SOURCE}/{DATASET}/dt=*/{name}.json.gz"):
        days |= {row["read_day"] for row in json.loads(gzip.decompress(path.read_bytes()))}
    return days


def _merge_and_save(ctx: Context, key: str, new_rows: List[Dict[str, Any]], identity: Tuple[str, ...], note: str) -> None:
    """A second run on one day adds to that day's file, because saving replaces a file."""
    if not new_rows:
        return
    path = BRONZE / SOURCE / DATASET / f"dt={ctx.snapshot}" / f"{key}.json.gz"
    existing = json.loads(gzip.decompress(path.read_bytes())) if path.exists() else []
    merged = {tuple(r[i] for i in identity): r for r in [*existing, *new_rows]}
    rows = [merged[k] for k in sorted(merged)]
    ctx.bronze.save_json(SOURCE, DATASET, key, rows, url=ARCHIVAL, method="POST", rows=len(rows), params={"factory": FACTORY}, note=note)
    ctx.bronze.flush()


def _newest_balance_day(snapshot: str) -> str:
    """Earlier snapshots hold the history, so a night saves only what it can add."""
    days = [""]
    for path in BRONZE.glob(f"{SOURCE}/{DATASET}/dt=*/foundation_balances.json.gz"):
        if path.parent.name < f"dt={snapshot}":
            days += [row["date_day"] for row in json.loads(gzip.decompress(path.read_bytes())) if "read_with" not in row]
    return max(days)


SCHEDULE_NOTE = ("assembled: each lockup's schedule from its contract state; owner, staking pool and account name dropped, "
                 "so a lockup is known only by its place in lockup.near's order")


@dataset(SOURCE, DATASET)
def lockups(ctx: Context) -> None:
    """Schedules of all lockups, the two accounts NEAR Explorer also subtracted, and the contracts' own answer to test against."""
    factory_transfers = _transfers(ctx, FACTORY)
    found = factory_lockups(factory_transfers)
    known = known_rows()
    now_ns = int(datetime.now(timezone.utc).timestamp()) * 10**9
    changed: List[Dict[str, Any]] = []
    first_reads = 0
    pending = 0

    def keep(row: Dict[str, Any]) -> None:
        nonlocal pending
        changed.append(row)
        known[row["lockup_no"]] = row
        pending += 1
        if pending >= 50:
            _merge_and_save(ctx, "schedules", changed, ("lockup_no",), SCHEDULE_NOTE)
            changed.clear()
            pending = 0

    next_lockup: Dict[int, int] = {}
    newest_by_name: Dict[str, int] = {}
    for number, (account, height, _) in enumerate(found, 1):
        if account in newest_by_name:
            next_lockup[newest_by_name[account]] = height
        newest_by_name[account] = number

    for number, (account, height, ns) in enumerate(found, 1):
        row = known.get(number)
        if row and int(row["created_height"]) != height:
            ctx.warn(f"lockup {number}: the factory's order no longer matches the stored rows, so it was left alone")
            continue
        if row is None or row.get("status") == "unread":
            if first_reads >= FIRST_READS_PER_RUN:
                continue
            first_reads += 1
            row = _first_read(ctx, number, account, height, ns)
            row = _follow_up(ctx, account, row, next_lockup.get(number)) if row["status"] == "live" else row
            keep(row)
        elif _can_still_change(row, now_ns) or (number in next_lockup and row.get("status") == "live"):
            updated = _follow_up(ctx, account, row, next_lockup.get(number))
            if updated != row:
                keep(updated)
    _merge_and_save(ctx, "schedules", changed, ("lockup_no",), SCHEDULE_NOTE)
    missing = sum(1 for number in range(1, len(found) + 1) if number not in known or known[number].get("status") == "unread")
    if missing:
        ctx.warn(f"{missing} of {len(found)} lockups not read yet; later runs continue")

    since = _newest_balance_day(ctx.snapshot)
    balances = [b for b in daily_balances(FACTORY, factory_transfers, ctx.snapshot) + daily_balances("contributors.near", _transfers(ctx, "contributors.near"), ctx.snapshot)
                if b["date_day"] >= since]
    for account in FOUNDATION_LOCKED:
        params = {"request_type": "view_account", "account_id": account, "finality": "final"}
        amount = (ctx.http.post(RPC, body("query", params), ok=(200, 422), headers=_headers()).json().get("result") or {}).get("amount")
        if amount:
            balances.append({"account_id": account, "date_day": ctx.snapshot, "balance_yocto": amount, "read_with": "view_account"})
    ctx.bronze.save_json(SOURCE, DATASET, "foundation_balances", balances, url=f"{TRANSFERS}/v0/transfers", method="POST", rows=len(balances),
                         params={"accounts": list(FOUNDATION_LOCKED)},
                         note="assembled: the end-of-day running balance per day with a native transfer, plus one view_account read per account; transfers themselves are not kept")

    by_number = {number: (account, known[number]) for number, (account, _, _) in enumerate(found, 1) if number in known and "lockup_amount" in known[number]}
    heights: Dict[str, int] = ctx.load_state("rpc__block_day", {})
    done = _saved_days("contract_views")
    note = "assembled: get_locked_amount and are_transfers_enabled at past blocks, per lockup number, to test the schedule formula"
    for read_day in VIEW_CHECK_DAYS:
        if read_day in done or read_day not in heights:
            continue
        sample = [(a, r) for n, (a, r) in sorted(by_number.items()) if n % VIEW_SAMPLE_EVERY == 0 and _existed_on(r, read_day, heights[read_day])
                  and heights[read_day] < next_lockup.get(n, 10**12)]
        _merge_and_save(ctx, "contract_views", _check_views(ctx, read_day, heights[read_day], sample), ("read_day", "lockup_no"), note)
    tip_read = [(a, r) for _, (a, r) in sorted(by_number.items()) if r.get("status") == "live" and schedule_end_ns(r) > now_ns]
    if tip_read and ctx.snapshot not in done:
        _merge_and_save(ctx, "contract_views", _check_views(ctx, ctx.snapshot, _tip_height(ctx) - 50, tip_read), ("read_day", "lockup_no"), note)
