"""NEAR's public BigQuery dataset, bigquery-public-data.crypto_near_mainnet_us, through BigQuery's REST API.

Access. BigQuery has no keyless route: every query runs as a job in a Google Cloud project of the reader's own. So
this needs GOOGLE_APPLICATION_CREDENTIALS, the path of a key file for a service account with the role BigQuery Job
User (the dataset itself is public), and the google-auth package, which is not in requirements.lock:
`pip install -r requirements-bigquery.txt`. Without either, these datasets are skipped and nothing else changes.

What is stored. The dataset holds every transaction and receipt since genesis: far too much to copy, and more about
single accounts than this repository keeps. Each query in ingest/sql/bigquery/ therefore aggregates on Google's side
and only the result comes back: counts per day, per day and contract, per month. The SQL file is the query as run, word
for word, and its SHA-256 and parameters are saved with every result.

What it costs. Google bills a query by the bytes of the columns it reads. The first 1 TB of each month is free, and a
project without a billing account is simply refused past that. Before a query runs it is sent as a dry run, which is
free and returns the bytes the query would read. A query over the per-query limit, or one that would take the month
past the monthly limit on this machine's own count, is not run; the real run carries the per-query limit as
maximumBytesBilled, so Google refuses it too.

The project's id is the reader's own, so it is kept out of everything saved: the manifest's URL carries a placeholder,
the reply is stored without its job reference, and error text has the id replaced.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..http import HttpError
from ..pipeline import Context, Skip, dataset
from ..settings import BRONZE, secret
from ._common import OVERLAP_DAYS

API = "https://bigquery.googleapis.com/bigquery/v2/projects/{project}"
SCOPE = "https://www.googleapis.com/auth/bigquery"
# No location is sent with a query: BigQuery runs a job where the tables it names live (us-east1 for this dataset, read
# on 2026-11-14), and a job told to run anywhere else is refused as if the table did not exist. Later calls about the
# job must name the place it ran, which the first reply gives.
SQL_DIR = Path(__file__).resolve().parents[1] / "sql" / "bigquery"
REQUIRES = ("GOOGLE_APPLICATION_CREDENTIALS",)
PAGE_ROWS = 20000
WAIT_MS = 50000  # how long one call waits for a running query before asking again
MAX_WAITS = 40  # about half an hour for one query
NOTE = ("Assembled from BigQuery's reply: rows keyed by the column names in its schema, values as the text BigQuery "
        "sent, and the job and project ids left out")

# Limits in GB of columns read. One month of the free allowance is 1,000 GB.
MAX_GB_PER_QUERY = 150.0
MAX_GB_PER_MONTH = 600.0

# The first read of each windowed query starts here; later reads take the last OVERLAP_DAYS days again.
GENESIS = date(2020, 7, 21)
# The day after hotwallet.kaiching's fixed batch and sweat-migration.near's key run stopped (docs/USAGE_BREAK_2026-04-02.md).
# Receipts ran near 20 million a day before it and near 4 million after, so an older window costs five times as much a day.
AFTER_USAGE_BREAK = date(2026, 4, 3)
FIRST_DAY = {
    "blocks_daily": GENESIS,
    # Where the rest of the warehouse turns from monthly to daily reads of the chain. The table holds 5.5 billion rows,
    # and the years before 2025 would cost about as much again to read.
    "transactions_daily": date(2025, 1, 1),
    "actions_daily": AFTER_USAGE_BREAK,
    # The same table and columns as transactions_daily, grouped by who signed, so the same start and the same cost.
    "signers_daily": date(2025, 1, 1),
    # receipt_actions again, for the callers of two contracts, from the same day as actions_daily.
    "callers_daily": AFTER_USAGE_BREAK,
    # The first day the dataset's table of staking balances holds. The whole table is about 5 GB.
    "staking_balances_daily": date(2023, 1, 1),
}
TOP_N = 25


@dataclass
class Session:
    project: str
    headers: Dict[str, str]


def _first_day_override(name: str) -> Optional[date]:
    """BIGQUERY_FIRST_DAY_<QUERY>=YYYY-MM-DD starts a first read somewhere else, for a longer history or a cheap test."""
    value = secret(f"BIGQUERY_FIRST_DAY_{name.upper()}")
    return date.fromisoformat(value) if value else None


def _limit_gb(name: str, default: float) -> float:
    return float(secret(name) or default)


def credentials() -> Tuple[str, str]:
    """An access token and the project to run jobs in. Skips, with the reason, when the key or the package is missing."""
    try:
        import google.auth
        from google.auth.transport.requests import Request
    except ImportError:
        raise Skip("needs the google-auth package: pip install -r requirements-bigquery.txt") from None
    path = os.path.expanduser(secret("GOOGLE_APPLICATION_CREDENTIALS") or "")
    if not os.path.isfile(path):
        raise Skip("GOOGLE_APPLICATION_CREDENTIALS does not name a file on this machine")
    found, key_project = google.auth.load_credentials_from_file(path, scopes=[SCOPE])
    project = secret("BIGQUERY_PROJECT") or key_project
    if not project:
        raise Skip("the key file names no project: set BIGQUERY_PROJECT to the Google Cloud project to run queries in")
    found.refresh(Request())
    return found.token, project


def open_session() -> Session:
    token, project = credentials()
    return Session(project, {"Authorization": f"Bearer {token}"})


def _scrub(text: str, project: str) -> str:
    return text.replace(project, "{project}")


def _call(ctx: Context, session: Session, method: str, path: str, *, body: Any = None, params: Optional[dict] = None) -> dict:
    """One API call. BigQuery explains a refusal in the reply's body, so 4xx replies are read, not thrown away."""
    url = API.format(project=session.project) + path
    public_url = API + path
    try:
        reply = ctx.http.request(method, url, params=params, json_body=body, headers=session.headers,
                                 ok=(200, 400, 403, 404), timeout=WAIT_MS // 1000 + 60, retries=4)
    except HttpError as e:
        raise HttpError(e.status, public_url, _scrub(str(e).split(": ", 1)[-1], session.project)) from None
    payload = reply.json()
    if reply.status != 200:
        message = ((payload.get("error") or {}).get("message") or str(payload))
        raise HttpError(reply.status, public_url, _scrub(message, session.project))
    return payload


def _parameter(name: str, value: Any) -> dict:
    kind = "DATE" if isinstance(value, date) else "INT64" if isinstance(value, int) else "STRING"
    text = value.isoformat() if isinstance(value, date) else str(value)
    return {"name": name, "parameterType": {"type": kind}, "parameterValue": {"value": text}}


def _rows(payload: dict, columns: List[str]) -> List[dict]:
    return [{name: cell.get("v") for name, cell in zip(columns, row["f"])} for row in payload.get("rows") or []]


def _month() -> str:
    """The calendar month Google counts the free allowance in."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _spent(ctx: Context, month: str) -> int:
    return int((ctx.load_state("bigquery_bytes", {}) or {}).get(month, 0))


def _add_spent(ctx: Context, month: str, billed: int) -> None:
    state = ctx.load_state("bigquery_bytes", {}) or {}
    state[month] = int(state.get(month, 0)) + billed
    ctx.save_state("bigquery_bytes", state)


def run_query(ctx: Context, session: Session, dataset_name: str, name: str, parameters: Dict[str, Any], key: str) -> Optional[int]:
    """Dry-run the query in ingest/sql/bigquery/<name>.sql, run it if it is within the limits, and save every page.

    Returns the number of rows saved, or None when the query was not run. The reason is then a warning, so the run
    reports the dataset as partial instead of quietly empty.
    """
    sql = (SQL_DIR / f"{name}.sql").read_text()
    body = {"query": sql, "useLegacySql": False, "parameterMode": "NAMED",
            "queryParameters": [_parameter(k, v) for k, v in parameters.items()]}
    saved_parameters = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in parameters.items()}

    estimate = int(_call(ctx, session, "POST", "/queries", body={**body, "dryRun": True}).get("totalBytesProcessed") or 0)
    per_query = _limit_gb("BIGQUERY_MAX_GB_PER_QUERY", MAX_GB_PER_QUERY)
    per_month = _limit_gb("BIGQUERY_MAX_GB_PER_MONTH", MAX_GB_PER_MONTH)
    month = _month()
    spent = _spent(ctx, month)
    if estimate > per_query * 1e9:
        ctx.warn(f"{name}: would read {estimate / 1e9:.1f} GB, over the limit of {per_query:g} GB a query; not run")
        return None
    if spent + estimate > per_month * 1e9:
        ctx.warn(f"{name}: would read {estimate / 1e9:.1f} GB on top of {spent / 1e9:.1f} GB this month, over the limit of {per_month:g} GB; not run")
        return None
    if secret("BIGQUERY_DRY_RUN"):
        ctx.warn(f"{name}: dry run only, would read {estimate / 1e9:.2f} GB; not run")
        return None

    reply = _call(ctx, session, "POST", "/queries", body={**body, "maximumBytesBilled": str(int(per_query * 1e9)),
                                                          "timeoutMs": WAIT_MS, "maxResults": PAGE_ROWS})
    job = (reply.get("jobReference") or {}).get("jobId")
    location = (reply.get("jobReference") or {}).get("location")
    waits = 0
    while not reply.get("jobComplete"):
        waits += 1
        if waits > MAX_WAITS:
            ctx.warn(f"{name}: still running after {MAX_WAITS * WAIT_MS // 60000} minutes; nothing saved")
            return None
        reply = _call(ctx, session, "GET", f"/queries/{job}", params={"location": location, "timeoutMs": WAIT_MS, "maxResults": PAGE_ROWS})

    columns = [{"name": f["name"], "type": f["type"]} for f in (reply.get("schema") or {}).get("fields", [])]
    names = [c["name"] for c in columns]
    billed = int(reply.get("totalBytesBilled") or reply.get("totalBytesProcessed") or 0)
    _add_spent(ctx, month, billed)
    head = {"query": name, "read_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sql_sha256": hashlib.sha256(sql.encode()).hexdigest(), "parameters": saved_parameters,
            "bytes_estimated": estimate, "bytes_processed": int(reply.get("totalBytesProcessed") or 0), "bytes_billed": billed,
            "cache_hit": bool(reply.get("cacheHit")), "total_rows": int(reply.get("totalRows") or 0), "columns": columns}
    page, saved = 0, 0
    while True:
        rows = _rows(reply, names)
        document = {**head, "page": page, "first_row": saved, "rows": rows}
        if page == 0:
            document["sql"] = sql
        ctx.bronze.save_json("bigquery", dataset_name, f"{key}__p{page:03d}", document, url=API + "/queries", method="POST",
                             params={"query": name, "sql_sha256": head["sql_sha256"], "parameters": saved_parameters},
                             rows=len(rows), note=NOTE)
        saved += len(rows)
        token = reply.get("pageToken")
        if not token or not rows:
            break
        page += 1
        reply = _call(ctx, session, "GET", f"/queries/{job}", params={"location": location, "pageToken": token, "maxResults": PAGE_ROWS})
    if saved != head["total_rows"]:
        ctx.warn(f"{name}: saved {saved} of {head['total_rows']} rows")
    return saved


def _newest_prior(ctx: Context, dataset_name: str) -> Optional[date]:
    """The newest earlier snapshot that holds this dataset, or None on a first read."""
    days = sorted(p.name[3:] for p in (BRONZE / "bigquery" / dataset_name).glob("dt=*") if p.name < f"dt={ctx.snapshot}" and any(p.iterdir()))
    return date.fromisoformat(days[-1]) if days else None


def window(ctx: Context, dataset_name: str, name: str) -> Tuple[date, date]:
    """The days a windowed query reads: everything from its first day on a first read, then a short overlap.

    The last day read is the day before the snapshot: the snapshot's own day is not over. A later read reaches back
    OVERLAP_DAYS before the newest earlier snapshot, however long ago that was, so a pause in the runs leaves no hole.
    """
    last = date.fromisoformat(ctx.snapshot) - timedelta(days=1)
    prior = _newest_prior(ctx, dataset_name)
    if prior is None:
        return _first_day_override(name) or FIRST_DAY[name], last
    return min(prior, last) - timedelta(days=OVERLAP_DAYS), last


def _key(first: date, last: date) -> str:
    return f"{first.isoformat()}__{last.isoformat()}"


@dataset("bigquery", "tables", requires=REQUIRES)
def tables(ctx: Context) -> None:
    """Every table's rows, size and last change. Free: it reads the dataset's list of tables."""
    run_query(ctx, open_session(), "tables", "tables", {}, "tables")


@dataset("bigquery", "partitions", requires=REQUIRES)
def partitions(ctx: Context) -> None:
    """Rows per day in every table, for the whole history, from the tables' partition records."""
    run_query(ctx, open_session(), "partitions", "partitions", {}, "partitions")


@dataset("bigquery", "circulating_supply", requires=REQUIRES)
def circulating_supply(ctx: Context) -> None:
    """NEAR's own daily circulating supply, a table of a few hundred KB, read whole."""
    run_query(ctx, open_session(), "circulating_supply", "circulating_supply", {}, "circulating_supply")


@dataset("bigquery", "blocks_daily", requires=REQUIRES)
def blocks_daily(ctx: Context) -> None:
    first, last = window(ctx, "blocks_daily", "blocks_daily")
    run_query(ctx, open_session(), "blocks_daily", "blocks_daily", {"first_day": first, "last_day": last}, _key(first, last))


@dataset("bigquery", "transactions_daily", requires=REQUIRES)
def transactions_daily(ctx: Context) -> None:
    first, last = window(ctx, "transactions_daily", "transactions_daily")
    run_query(ctx, open_session(), "transactions_daily", "transactions_daily",
              {"first_day": first, "last_day": last, "top_n": TOP_N}, _key(first, last))


@dataset("bigquery", "actions_daily", requires=REQUIRES)
def actions_daily(ctx: Context) -> None:
    first, last = window(ctx, "actions_daily", "actions_daily")
    run_query(ctx, open_session(), "actions_daily", "actions_daily",
              {"first_day": first, "last_day": last, "top_n": TOP_N}, _key(first, last))


@dataset("bigquery", "signers_daily", requires=REQUIRES)
def signers_daily(ctx: Context) -> None:
    """Each day's largest signers, and the largest senders of the transactions NEAR Intents' contract receives.

    A first read from 2025-01-01 was 126 GB on 2026-11-14; a later read takes the last few days."""
    first, last = window(ctx, "signers_daily", "signers_daily")
    run_query(ctx, open_session(), "signers_daily", "signers_daily",
              {"first_day": first, "last_day": last, "top_n": TOP_N}, _key(first, last))


@dataset("bigquery", "callers_daily", requires=REQUIRES)
def callers_daily(ctx: Context) -> None:
    """Each day's largest callers of the Chain Signatures contract and of NEAR Intents' contract.

    A first read from 2026-04-03 was 50 GB on 2026-11-14; a later read takes the last few days."""
    first, last = window(ctx, "callers_daily", "callers_daily")
    run_query(ctx, open_session(), "callers_daily", "callers_daily",
              {"first_day": first, "last_day": last, "top_n": TOP_N}, _key(first, last))


@dataset("bigquery", "staking_balances_daily", requires=REQUIRES)
def staking_balances_daily(ctx: Context) -> None:
    """Staked NEAR by day and how much of it the largest holders have, from the table named ft_balances_daily."""
    first, last = window(ctx, "staking_balances_daily", "staking_balances_daily")
    run_query(ctx, open_session(), "staking_balances_daily", "staking_balances_daily",
              {"first_day": first, "last_day": last}, _key(first, last))


@dataset("bigquery", "signer_cohorts", profile="backfill", requires=REQUIRES)
def signer_cohorts(ctx: Context) -> None:
    """Reads every transaction's signer and day since genesis, so it is started by hand, not every night.

    At 155 GB on 2026-11-14 it is over the per-query limit, so it runs only with BIGQUERY_MAX_GB_PER_QUERY raised for
    the run: a query this size should be a decision each time, not a default."""
    last = date.fromisoformat(ctx.snapshot) - timedelta(days=1)
    run_query(ctx, open_session(), "signer_cohorts", "signer_cohorts", {"last_day": last}, f"through__{last.isoformat()}")
