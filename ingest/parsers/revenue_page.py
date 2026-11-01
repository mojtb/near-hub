"""Pull the data embedded in revenue.near.org out of its Next.js flight payload.

The page renders its tiles as 0 in plain HTML, but passes the real numbers to its components as
props inside `self.__next_f.push([1,"..."])`. This parser decodes that string and reads each named
series with a JSON decoder. It raises if an expected series disappears, so a page redesign fails
loudly instead of quietly producing empty tables.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict

REQUIRED_ARRAYS = ("totalFeesSeries", "intentVolumeSeries", "revenueSeries", "absoluteRevEmissions",
                   "emissionsMonthly", "tvlChartSeries", "stats")
OPTIONAL_ARRAYS = ("rows", "items")
_PUSH = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', re.S)
_UPDATED = re.compile(r"Updated\s*(?:·|&#183;|&middot;)?\s*(?:<!-- -->)?\s*([A-Z][a-z]{2} \d{1,2}, \d{4})")


def flight_payload(html: str) -> str:
    chunks = _PUSH.findall(html)
    if not chunks:
        raise ValueError("revenue page: no flight payload found")
    return "".join(json.loads(f'"{chunk}"') for chunk in chunks)


def _array(blob: str, name: str) -> Any:
    marker = f'"{name}":['
    start = blob.find(marker)
    if start < 0:
        return None
    value, _ = json.JSONDecoder().raw_decode(blob, start + len(marker) - 1)
    return value


def _capture_rates(blob: str) -> Dict[str, Any]:
    start = blob.find('{"pp_fe_all_time"')
    if start < 0:
        raise ValueError("revenue page: capture-rate object not found")
    value, _ = json.JSONDecoder().raw_decode(blob, start)
    return value


def parse(html: str) -> Dict[str, Any]:
    blob = flight_payload(html)
    parsed: Dict[str, Any] = {}
    for name in REQUIRED_ARRAYS:
        value = _array(blob, name)
        if not value:
            raise ValueError(f"revenue page: expected series {name!r} is missing or empty")
        parsed[name] = value
    for name in OPTIONAL_ARRAYS:
        parsed[name] = _array(blob, name) or []
    parsed["captureRates"] = _capture_rates(blob)
    updated = _UPDATED.search(html)
    parsed["pageUpdated"] = updated.group(1) if updated else None
    return parsed
