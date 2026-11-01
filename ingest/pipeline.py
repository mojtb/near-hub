"""Dataset registry and runner.

One failing source never stops the others. Every run ends with a status table and a
run report in data/bronze/_runs/, so a skipped or failed dataset is visible rather than
silently missing.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .bronze import BronzeWriter
from .http import BudgetExceeded, HttpClient, HttpError
from .settings import BRONZE, STATE, secret


def log(message: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


class Skip(Exception):
    """Raised by a dataset to report that it did not run, and why."""


@dataclass
class Context:
    snapshot: str
    http: HttpClient
    bronze: BronzeWriter
    warnings: List[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        log(f"  warning: {message}")

    def load_state(self, name: str, default=None):
        path = STATE / f"{name}.json"
        return json.loads(path.read_text()) if path.exists() else default

    def save_state(self, name: str, value) -> None:
        STATE.mkdir(parents=True, exist_ok=True)
        (STATE / f"{name}.json").write_text(json.dumps(value, indent=1, sort_keys=True) + "\n")


@dataclass(frozen=True)
class Dataset:
    source: str
    name: str
    fn: Callable[[Context], None]
    profile: str = "nightly"  # "nightly" runs every night; "backfill" is a long job started by hand
    requires: Tuple[str, ...] = ()  # environment variables without which the dataset is skipped


REGISTRY: List[Dataset] = []


def dataset(source: str, name: str, profile: str = "nightly", requires: Sequence[str] = ()):
    """Decorator that registers a fetch function."""
    def register(fn: Callable[[Context], None]):
        REGISTRY.append(Dataset(source, name, fn, profile, tuple(requires)))
        return fn
    return register


def select(profile: str, sources: Optional[List[str]], names: Optional[List[str]]) -> List[Dataset]:
    chosen = []
    for d in REGISTRY:
        if profile != "all" and d.profile != profile:
            continue
        if sources and d.source not in sources:
            continue
        if names and d.name not in names:
            continue
        chosen.append(d)
    return chosen


def run(snapshot: str, datasets: List[Dataset]) -> Dict[str, dict]:
    http = HttpClient(log=log)
    bronze = BronzeWriter(snapshot)
    results: Dict[str, dict] = {}
    for d in datasets:
        label = f"{d.source}/{d.name}"
        missing = [v for v in d.requires if not secret(v)]
        if missing:
            results[label] = {"status": "skipped", "detail": f"needs {', '.join(missing)}", "seconds": 0}
            log(f"{label}: skipped (needs {', '.join(missing)})")
            continue
        log(f"{label}: start")
        ctx = Context(snapshot, http, bronze)
        started = time.monotonic()
        before = len(bronze._entries)
        try:
            d.fn(ctx)
            status, detail = ("partial", "; ".join(ctx.warnings)[:500]) if ctx.warnings else ("ok", "")
        except Skip as e:
            status, detail = "skipped", str(e)
        except (HttpError, BudgetExceeded) as e:
            status, detail = "failed", str(e)
        except Exception as e:  # a bug in one source must not lose the others
            status, detail = "failed", f"{type(e).__name__}: {e}"
            traceback.print_exc()
        bronze.flush()
        results[label] = {"status": status, "detail": detail, "seconds": round(time.monotonic() - started, 1),
                          "files": len(bronze._entries) - before}
        log(f"{label}: {status} ({results[label]['files']} files, {results[label]['seconds']}s){' ' + detail if detail else ''}")
    _write_report(snapshot, results)
    return results


def _write_report(snapshot: str, results: Dict[str, dict]) -> None:
    path = BRONZE / "_runs" / f"dt={snapshot}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = json.loads(path.read_text()) if path.exists() else {}
    merged.update(results)
    path.write_text(json.dumps(merged, indent=1, sort_keys=True) + "\n")


def print_summary(results: Dict[str, dict]) -> None:
    width = max((len(k) for k in results), default=10)
    print(f"\n{'dataset':<{width}}  {'status':<8} {'files':>5} {'secs':>7}  detail")
    for label, r in results.items():
        print(f"{label:<{width}}  {r['status']:<8} {r.get('files', 0):>5} {r['seconds']:>7}  {r['detail'][:90]}")
    counts: Dict[str, int] = {}
    for r in results.values():
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("\n" + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
