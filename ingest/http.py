"""HTTP client: per-host pacing, polite retries, optional daily budgets.

Replies keep the exact bytes the server sent, because bronze stores them unchanged.
"""
from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

import requests

from .settings import USER_AGENT, secret


class HttpError(RuntimeError):
    def __init__(self, status: int, url: str, preview: str = ""):
        super().__init__(f"HTTP {status} from {url}: {preview[:160]}")
        self.status = status
        self.url = url


class BudgetExceeded(RuntimeError):
    """The daily call budget for a host is spent; stop calling it until tomorrow."""


@dataclass
class Reply:
    status: int
    content: bytes
    url: str
    headers: Dict[str, str] = field(default_factory=dict)

    def json(self) -> Any:
        return json.loads(self.content)


@dataclass
class HostPolicy:
    min_interval: float = 0.0
    daily_budget: Optional[int] = None
    base_backoff: float = 5.0
    calls: int = 0
    last_call: float = 0.0


def _nearblocks_interval() -> float:
    rpm = float(secret("NEARBLOCKS_RPM") or 5.7)
    return 60.0 / rpm


def default_policies() -> Dict[str, HostPolicy]:
    """Limits are the published ones where they exist, and observed ones otherwise."""
    # Keyless FastNear returned 429 after about 10 quick calls, so stay near 9 per minute without a key.
    fastnear = 0.15 if secret("FASTNEAR_API_KEY") else 6.5
    fastnear_backoff = 5.0 if secret("FASTNEAR_API_KEY") else 60.0
    return {
        "api.nearblocks.io": HostPolicy(_nearblocks_interval(), daily_budget=None if secret("NEARBLOCKS_API_KEY") else 320, base_backoff=30.0),
        "api.fastnear.com": HostPolicy(fastnear, base_backoff=fastnear_backoff),
        "tx.main.fastnear.com": HostPolicy(fastnear, base_backoff=fastnear_backoff),
        "transfers.main.fastnear.com": HostPolicy(fastnear, base_backoff=fastnear_backoff),
        "free.rpc.fastnear.com": HostPolicy(0.15 if secret("FASTNEAR_API_KEY") else 1.0, base_backoff=20.0),
        "archival-rpc.mainnet.fastnear.com": HostPolicy(1.5, base_backoff=20.0),  # shows no sign of reading a key, so the keyless pace stays
        "mainnet.neardata.xyz": HostPolicy(1.0, base_backoff=30.0),  # published: 180 per minute per IP; 429s came sooner
        "explorer.near-intents.org": HostPolicy(5.6, base_backoff=30.0),  # published: 1 per 5 s per partner; 5.2 s still drew some 429s
        "api.exchange.coinbase.com": HostPolicy(0.5),
        "community-api.coinmetrics.io": HostPolicy(6.5, base_backoff=30.0),  # published: 10 per 6 s per IP
        "api.llama.fi": HostPolicy(0.5),
        "coins.llama.fi": HostPolicy(0.5),
        "stablecoins.llama.fi": HostPolicy(0.5),
        "api.github.com": HostPolicy(0.75 if secret("GITHUB_TOKEN") else 60.0, base_backoff=60.0),
        "gov.near.org": HostPolicy(2.0, base_backoff=30.0),
    }


class HttpClient:
    def __init__(self, policies: Optional[Dict[str, HostPolicy]] = None, log=print):
        self.policies = default_policies() if policies is None else policies
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"})
        self.log = log

    def _policy(self, url: str) -> HostPolicy:
        host = url.split("/")[2]
        return self.policies.setdefault(host, HostPolicy())

    def _pace(self, policy: HostPolicy, url: str) -> None:
        if policy.daily_budget is not None and policy.calls >= policy.daily_budget:
            raise BudgetExceeded(f"daily budget of {policy.daily_budget} calls spent for {url.split('/')[2]}")
        wait = policy.min_interval - (time.monotonic() - policy.last_call)
        if wait > 0:
            time.sleep(wait)
        policy.last_call = time.monotonic()
        policy.calls += 1

    def request(self, method: str, url: str, *, params: Optional[dict] = None, json_body: Any = None,
                headers: Optional[dict] = None, ok: Iterable[int] = (200,), timeout: int = 90,
                retries: int = 6) -> Reply:
        policy = self._policy(url)
        ok = tuple(ok)
        last_error: Optional[str] = None
        for attempt in range(retries):
            self._pace(policy, url)
            try:
                r = self.session.request(method, url, params=params, json=json_body, headers=headers, timeout=timeout)
            except requests.RequestException as e:
                last_error = f"{type(e).__name__}: {e}"
                self._sleep(policy, attempt, url, last_error)
                continue
            if r.status_code in ok:
                return Reply(r.status_code, r.content, r.url, dict(r.headers))
            if r.status_code == 429 or r.status_code >= 500:
                last_error = f"HTTP {r.status_code}"
                self._sleep(policy, attempt, url, last_error, r.headers.get("Retry-After"))
                continue
            raise HttpError(r.status_code, url, r.text)
        raise HttpError(0, url, f"gave up after {retries} attempts; last error: {last_error}")

    def _sleep(self, policy: HostPolicy, attempt: int, url: str, why: str, retry_after: Optional[str] = None) -> None:
        delay = min(policy.base_backoff * (2 ** attempt), 300.0) * (1 + random.random() * 0.1)
        if retry_after and retry_after.replace(".", "", 1).isdigit():
            delay = max(delay, float(retry_after))
        self.log(f"  {why} from {url.split('/')[2]}; waiting {delay:.0f}s")
        time.sleep(delay)

    def get(self, url: str, **kw: Any) -> Reply:
        return self.request("GET", url, **kw)

    def post(self, url: str, body: Any = None, **kw: Any) -> Reply:
        return self.request("POST", url, json_body=body, **kw)
