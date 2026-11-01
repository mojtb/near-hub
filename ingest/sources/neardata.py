"""Usage composition from evenly spaced sample blocks (Neardata, no key, 180 requests per minute).

Answers "who is the activity for?" without a warehouse of raw blocks. For a past UTC day, this
fetches N blocks spread evenly across that day and counts transactions and receipts per receiver.
A sample is an estimate, so every row keeps blocks_sampled, and raw blocks are discarded after
counting: about 265 KB per block would otherwise be far too much to store.
"""
from __future__ import annotations

import gzip
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any, Dict, Iterable, Optional

from ..pipeline import Context, Skip, dataset
from ..settings import BRONZE

SOURCE = "neardata"
BASE = "https://mainnet.neardata.xyz/v0/block"
BLOCKS_PER_DAY = 96
BACKFILL_BLOCKS_PER_DAY = 24
BACKFILL_DAYS_PER_RUN = 20


def _day_heights() -> Dict[str, int]:
    """Day to first-block height, from the block_day bronze files."""
    heights: Dict[str, int] = {}
    for path in sorted(BRONZE.glob("rpc/block_day/dt=*/*.json.gz")):
        for row in json.loads(gzip.decompress(path.read_bytes())):
            heights[row["day"]] = row["height"]
    return heights


def _block(ctx: Context, height: int) -> Optional[Dict[str, Any]]:
    """The block at this height, or the next existing one. Neardata answers null for skipped heights."""
    for offset in range(6):
        reply = ctx.http.get(f"{BASE}/{height + offset}", timeout=120)
        payload = reply.json()
        if payload:
            return payload
    return None


def tally(blocks: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Count activity per receiver across blocks. Pure function, unit-tested."""
    txns: Counter = Counter()
    receipts: Counter = Counter()
    signers: Dict[str, set] = defaultdict(set)
    gas_burnt: Counter = Counter()
    tokens_burnt: Counter = Counter()
    action_kinds: Counter = Counter()
    n_blocks = n_txns = n_receipts = 0
    for block in blocks:
        n_blocks += 1
        for shard in block.get("shards") or []:
            chunk = shard.get("chunk") or {}
            for item in chunk.get("transactions") or []:
                tx = item.get("transaction") or {}
                receiver = tx.get("receiver_id")
                n_txns += 1
                txns[receiver] += 1
                if tx.get("signer_id"):
                    signers[receiver].add(tx["signer_id"])
                for action in tx.get("actions") or []:
                    action_kinds[next(iter(action)) if isinstance(action, dict) else str(action)] += 1
            for outcome in shard.get("receipt_execution_outcomes") or []:
                receipt = outcome.get("receipt") or {}
                receiver = receipt.get("receiver_id")
                result = (outcome.get("execution_outcome") or {}).get("outcome") or {}
                n_receipts += 1
                receipts[receiver] += 1
                gas_burnt[receiver] += int(result.get("gas_burnt") or 0)
                tokens_burnt[receiver] += int(result.get("tokens_burnt") or 0)
    accounts = sorted(set(txns) | set(receipts), key=lambda a: (-(receipts[a] + txns[a]), str(a)))
    return {
        "blocks_sampled": n_blocks,
        "txns_sampled": n_txns,
        "receipts_sampled": n_receipts,
        "action_kinds": dict(action_kinds.most_common()),
        "receivers": [{"account_id": a, "txns": txns[a], "receipts": receipts[a], "distinct_signers": len(signers[a]),
                       "gas_burnt": gas_burnt[a], "tokens_burnt_yocto": str(tokens_burnt[a])}
                      for a in accounts if a],
    }


def _sample_day(ctx: Context, day: date, heights: Dict[str, int], n: int) -> bool:
    start, end = heights.get(day.isoformat()), heights.get((day + timedelta(days=1)).isoformat())
    if not start or not end:
        ctx.warn(f"{day}: no block heights known yet, run rpc/block_day first")
        return False
    picks = [start + int((i + 0.5) * (end - start) / n) for i in range(n)]
    # One at a time: three parallel workers hit 429 from this IP well below the published limit.
    found = [b for b in (_block(ctx, h) for h in picks) if b]
    summary = tally(found)
    summary.update({"day": day.isoformat(), "blocks_in_day": end - start, "first_height": start, "last_height": end - 1})
    ctx.bronze.save_json(SOURCE, "receiver_sample", day.isoformat(), summary, url=BASE, rows=len(summary["receivers"]),
                         note=f"aggregated from {len(found)} evenly spaced blocks; raw blocks discarded")
    return True


@dataset(SOURCE, "receiver_sample")
def receiver_sample(ctx: Context) -> None:
    """The last complete UTC day, plus any recent day missed in earlier runs."""
    heights = _day_heights()
    done = ctx.load_state("neardata__receiver_sample", {})
    today = date.fromisoformat(ctx.snapshot)
    for back in range(1, 4):
        day = today - timedelta(days=back)
        if day.isoformat() not in done and _sample_day(ctx, day, heights, BLOCKS_PER_DAY):
            done[day.isoformat()] = BLOCKS_PER_DAY
            ctx.save_state("neardata__receiver_sample", done)


@dataset(SOURCE, "receiver_sample_backfill", profile="backfill")
def receiver_sample_backfill(ctx: Context) -> None:
    """Lower-density sample of past days, newest first, resumable across runs."""
    heights = _day_heights()
    if not heights:
        raise Skip("run rpc/block_day first")
    done = ctx.load_state("neardata__receiver_sample", {})
    today = date.fromisoformat(ctx.snapshot)
    days = [today - timedelta(days=b) for b in range(1, 366)]
    todo = [d for d in days if d.isoformat() not in done and d.isoformat() in heights and (d + timedelta(days=1)).isoformat() in heights]
    for day in todo[:BACKFILL_DAYS_PER_RUN]:
        if _sample_day(ctx, day, heights, BACKFILL_BLOCKS_PER_DAY):
            done[day.isoformat()] = BACKFILL_BLOCKS_PER_DAY
            ctx.save_state("neardata__receiver_sample", done)
