"""Helpers shared by the source modules."""
from __future__ import annotations

from typing import Any, Iterable, Optional

from ..bronze import safe_key
from ..http import HttpError, Reply
from ..pipeline import Context
from ..settings import BRONZE

# First run asks for the longest window an endpoint allows, later runs only for a short
# overlap: history accumulates across snapshots, and the overlap reveals restated values.
FIRST_RUN_DAYS = 365
OVERLAP_DAYS = 14


def has_prior(ctx: Context, source: str, dataset: str, key: str = "*") -> bool:
    """True if an earlier snapshot already holds this key, in any file format."""
    pattern = f"{source}/{dataset}/dt=*/{safe_key(key) if key != '*' else '*'}.*.gz"
    return any(p.parent.name < f"dt={ctx.snapshot}" for p in BRONZE.glob(pattern))


def window_days(ctx: Context, source: str, dataset: str, key: str = "*") -> int:
    return OVERLAP_DAYS if has_prior(ctx, source, dataset, key) else FIRST_RUN_DAYS


def fetch(ctx: Context, source: str, dataset: str, key: str, url: str, *, params: Optional[dict] = None,
          headers: Optional[dict] = None, method: str = "GET", body: Any = None, ok: Iterable[int] = (200,),
          ext: str = "json", note: str = "", timeout: int = 120) -> Optional[Reply]:
    """Fetch and save one response. A failed key becomes a warning, so one bad key cannot lose the rest."""
    try:
        reply = ctx.http.request(method, url, params=params, json_body=body, headers=headers, ok=ok, timeout=timeout)
    except HttpError as e:
        ctx.warn(f"{key}: {e}")
        return None
    saved_params = dict(params or {})
    if body is not None:
        saved_params["body"] = body
    ctx.bronze.save(source, dataset, key, reply.content, url=url, method=method, params=saved_params,
                    status=reply.status, ext=ext, note=note)
    return reply
