"""Parse Prometheus text exposition into {metric: value}. Lines with labels or non-numeric values are skipped."""
from __future__ import annotations

from typing import Dict


def parse(text: str) -> Dict[str, float]:
    metrics: Dict[str, float] = {}
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) != 2 or line.startswith("#") or "{" in parts[0]:
            continue
        try:
            metrics[parts[0]] = float(parts[1])
        except ValueError:
            continue
    return metrics
