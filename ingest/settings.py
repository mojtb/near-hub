"""Paths and credentials shared by every source.

Credentials come from the environment or a local .env file, and only ever travel in
request headers, so they cannot end up in a saved URL or in the manifest.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
BRONZE = DATA / "bronze"
STATE = DATA / "state"
REGISTRY = ROOT / "registry"
USER_AGENT = "near-thesis/0.1 (NEAR HACKATHON research; github.com/mojtb/near-thesis)"


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Read KEY=VALUE lines from .env without overriding the real environment."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def secret(name: str) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value or None


def read_registry(name: str) -> List[Dict[str, str]]:
    """Rows of registry/<name>.csv as dicts. The same files are loaded as dbt seeds."""
    with (REGISTRY / f"{name}.csv").open(newline="") as f:
        return list(csv.DictReader(f))
