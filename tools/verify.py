"""`make verify`: every promise the warehouse makes, checked offline. Prints `N/N checks passed`.

Needs no network and no keys. It reads committed bronze and the warehouse built by `make warehouse`.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Tuple

import duckdb

from tools.catalog import expected_results, source_table, verdict
from tools.export_gold import FINGERPRINTS, ROOT, WAREHOUSE, fingerprints

BRONZE = ROOT / "data" / "bronze"
Result = Tuple[bool, str]

# Shapes of real credentials. Plain words like "Bearer" in source code are fine; values are not.
SECRET_PATTERNS = [
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{20,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\."),
    re.compile(r"\bgh[opsu]_[A-Za-z0-9]{20,}"),
    re.compile(r"apiKey=[A-Za-z0-9]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".sql", ".csv", ".json", ".jsonl", ".txt", ".toml", ".lock", ""}


def _manifest_entries() -> List[dict]:
    entries = []
    for path in sorted((BRONZE / "_manifest").glob("dt=*.jsonl")):
        entries.extend(json.loads(line) for line in path.read_text().splitlines() if line)
    return entries


def check_manifest_complete() -> Result:
    listed = {e["path"] for e in _manifest_entries()}
    on_disk = {str(p.relative_to(BRONZE)) for p in BRONZE.glob("*/*/dt=*/*.gz")}
    unlisted, missing = on_disk - listed, listed - on_disk
    if unlisted or missing:
        return False, f"{len(unlisted)} files not in a manifest, {len(missing)} manifest lines without a file: {sorted(unlisted | missing)[:3]}"
    return True, f"{len(listed)} bronze files, all listed"


def check_hashes() -> Result:
    bad = []
    entries = _manifest_entries()
    for e in entries:
        raw = gzip.decompress((BRONZE / e["path"]).read_bytes())
        if hashlib.sha256(raw).hexdigest() != e["sha256"]:
            bad.append(e["path"])
    return (not bad), f"{len(entries)} SHA-256 hashes match" if not bad else f"{len(bad)} files changed since fetch: {bad[:3]}"


def _committed_text_files() -> List[Path]:
    skip_dirs = {".venv", ".git", "target", "logs", "__pycache__", ".pytest_cache", ".logs", "bronze", "gold"}
    found = []
    for path in ROOT.rglob("*"):
        if path.is_file() and path.name != ".env" and path.suffix in TEXT_SUFFIXES and not (set(path.relative_to(ROOT).parts) & skip_dirs):
            found.append(path)
    found.extend((BRONZE / "_manifest").glob("*.jsonl"))
    return found


def check_no_secrets() -> Result:
    hits = []
    files = _committed_text_files()
    for path in files:
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                hits.append(str(path.relative_to(ROOT)))
    return (not hits), f"{len(files)} files scanned, no credential shapes" if not hits else f"possible secret in {sorted(set(hits))[:5]}"


def _connect() -> duckdb.DuckDBPyConnection:
    os.chdir(ROOT)
    return duckdb.connect("data/warehouse.duckdb", read_only=True)


def check_warehouse_built() -> Result:
    if not WAREHOUSE.exists():
        return False, "data/warehouse.duckdb is missing; run `make warehouse` first"
    con = _connect()
    counts = dict(con.execute("select table_schema, count(*) from information_schema.tables where table_schema in ('silver', 'gold', 'registry') group by 1").fetchall())
    return (counts.get("gold", 0) > 0), f"{counts.get('gold', 0)} gold, {counts.get('silver', 0)} silver, {counts.get('registry', 0)} registry tables"


def check_dbt_tests() -> Result:
    pinned = ROOT / "data" / "PINNED"
    as_of = os.environ.get("AS_OF") or (pinned.read_text().strip() if pinned.exists() else "9999-12-31")
    env = {**os.environ, "DBT_PROFILES_DIR": ".", "DBT_TARGET_PATH": "warehouse/target", "DBT_LOG_PATH": "warehouse/logs"}
    dbt = str(ROOT / ".venv" / "bin" / "dbt")
    run = subprocess.run([dbt, "test", "--quiet", "--vars", f'{{as_of: "{as_of}"}}'], cwd=ROOT, env=env, capture_output=True, text=True)
    results = json.loads((ROOT / "warehouse" / "target" / "run_results.json").read_text())["results"]
    failed = [r["unique_id"].split(".", 2)[-1] for r in results if r["status"] != "pass"]
    if failed or run.returncode != 0:
        return False, f"{len(failed)} of {len(results)} data tests failed: {failed[:5]}"
    return True, f"{len(results)} data tests pass"


def check_gold_documented() -> Result:
    manifest = json.loads((ROOT / "warehouse" / "target" / "manifest.json").read_text())
    documented = {n["name"]: n["columns"] for n in manifest["nodes"].values()
                  if n["resource_type"] == "model" and n["schema"] == "gold"}
    con = _connect()
    gaps, total = [], 0
    for table, column in con.execute("select table_name, column_name from information_schema.columns where table_schema = 'gold'").fetchall():
        total += 1
        doc = documented.get(table, {}).get(column)
        if not doc or not doc.get("description") or not (doc.get("meta") or doc.get("config", {}).get("meta", {})).get("unit"):
            gaps.append(f"{table}.{column}")
    return (not gaps), f"{total} gold columns have a description and unit" if not gaps else f"{len(gaps)} undocumented: {gaps[:5]}"


def check_reconciliation() -> Result:
    con = _connect()
    counts = dict(con.execute("select status, count(*) from gold.dq_reconciliation group by 1").fetchall())
    unexplained = con.execute("select count(*) from gold.dq_reconciliation where status = 'differs' and explanation is null").fetchone()[0]
    summary = ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))
    return (unexplained == 0), f"{summary}; {unexplained} unexplained"


def check_fingerprints() -> Result:
    if not FINGERPRINTS.exists():
        return False, "data/gold/_fingerprints.json is missing"
    expected = json.loads(FINGERPRINTS.read_text())
    actual = fingerprints(_connect())
    changed = sorted(t for t in set(expected) | set(actual) if expected.get(t) != actual.get(t))
    return (not changed), f"{len(actual)} gold tables reproduce the committed fingerprints" if not changed else f"{len(changed)} tables differ: {changed[:6]}"


def check_readme_results() -> Result:
    """Both generated blocks: the README's expected results and the data notice's table of sources."""
    con = _connect()
    missing = sorted({name for name, body, path in (("README.md", verdict(con), ROOT / "README.md"),
                                                    ("README.md", expected_results(con), ROOT / "README.md"),
                                                    ("DATA_NOTICE.md", source_table(con), ROOT / "DATA_NOTICE.md"))
                      if body not in path.read_text()})
    if missing:
        return False, f"{' and '.join(missing)} no longer match the warehouse; run `make catalog`"
    return True, "the README's result and expected numbers and the data notice's sources match the warehouse"


def check_unit_tests() -> Result:
    run = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=ROOT, capture_output=True, text=True)
    last = (run.stdout.strip().splitlines() or ["no output"])[-1]
    return run.returncode == 0, f"pytest: {last}"


CHECKS: List[Tuple[str, Callable[[], Result]]] = [
    ("bronze manifest is complete", check_manifest_complete),
    ("bronze files match their hashes", check_hashes),
    ("no credentials in the repository", check_no_secrets),
    ("warehouse is built", check_warehouse_built),
    ("data tests pass", check_dbt_tests),
    ("every gold column is documented", check_gold_documented),
    ("reconciliation gaps are explained", check_reconciliation),
    ("gold tables reproduce their fingerprints", check_fingerprints),
    ("the README and the data notice are current", check_readme_results),
    ("unit tests pass", check_unit_tests),
]


def main() -> int:
    passed = 0
    for name, check in CHECKS:
        try:
            ok, detail = check()
        except Exception as e:  # a check that cannot run counts as failed, with the reason shown
            ok, detail = False, f"{type(e).__name__}: {e}"
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {detail}", flush=True)
    print(f"\n{passed}/{len(CHECKS)} checks passed")
    return 0 if passed == len(CHECKS) else 1


if __name__ == "__main__":
    sys.exit(main())
