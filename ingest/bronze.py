"""Bronze: raw responses as received, gzipped, with one manifest line per file.

Layout:   data/bronze/<source>/<dataset>/dt=<YYYY-MM-DD>/<key>.<ext>.gz
Manifest: data/bronze/_manifest/dt=<YYYY-MM-DD>.jsonl

`sha256` hashes the uncompressed bytes, and gzip runs with mtime=0, so the same response
always produces the same file. Secrets never reach this module: credentials travel only
in headers, and the manifest records just the URL and parameters.
"""
from __future__ import annotations

import fcntl
import gzip
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .settings import BRONZE

_SAFE_KEY = re.compile(r"[^A-Za-z0-9._-]+")


def safe_key(key: str) -> str:
    return _SAFE_KEY.sub("_", key).strip("_") or "all"


class BronzeWriter:
    def __init__(self, snapshot: str, root: Path = BRONZE):
        self.snapshot = snapshot
        self.root = root
        self.manifest_path = root / "_manifest" / f"dt={snapshot}.jsonl"
        self._entries: Dict[str, dict] = {}
        self._own: Dict[str, dict] = {}  # the lines this writer saved itself: the only ones it writes back
        self._unflushed = 0
        if self.manifest_path.exists():
            for line in self.manifest_path.read_text().splitlines():
                entry = json.loads(line)
                self._entries[entry["path"]] = entry

    def save(self, source: str, dataset: str, key: str, raw: bytes, *, url: str, method: str = "GET",
             params: Optional[dict] = None, status: int = 200, ext: str = "json", rows: Optional[int] = None,
             note: str = "") -> Path:
        relative = f"{source}/{dataset}/dt={self.snapshot}/{safe_key(key)}.{ext}.gz"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        packed = gzip.compress(raw, compresslevel=9, mtime=0)
        path.write_bytes(packed)
        self._own[relative] = self._entries[relative] = {
            "path": relative,
            "source": source,
            "dataset": dataset,
            "key": safe_key(key),
            "snapshot": self.snapshot,
            "url": url,
            "method": method,
            "params": params or {},
            "status": status,
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "gz_bytes": len(packed),
            "rows": rows,
            "note": note,
        }
        self._unflushed += 1
        if self._unflushed >= 25:
            self.flush()
        return path

    def save_json(self, source: str, dataset: str, key: str, payload: Any, **kw: Any) -> Path:
        """For payloads we assembled or trimmed ourselves. `note` must say what changed."""
        raw = json.dumps(payload, separators=(",", ":"), sort_keys=False).encode()
        return self.save(source, dataset, key, raw, **kw)

    def flush(self) -> None:
        """Add this writer's own lines to what is on disk, under a lock, so parallel runs on one day lose nothing.

        Only the lines this writer saved go back. The ones it read when it started may be older than what another run
        has saved since, and writing them back would leave a newer file listed under its old hash.
        """
        if not self._own:
            return
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.manifest_path.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            merged: Dict[str, dict] = {}
            if self.manifest_path.exists():
                for line in self.manifest_path.read_text().splitlines():
                    entry = json.loads(line)
                    merged[entry["path"]] = entry
            merged.update(self._own)
            lines = [json.dumps(merged[k], sort_keys=True) for k in sorted(merged)]
            temporary = self.manifest_path.with_suffix(".tmp")
            temporary.write_text("\n".join(lines) + "\n")
            temporary.replace(self.manifest_path)
        self._unflushed = 0
