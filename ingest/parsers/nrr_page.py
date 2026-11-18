"""Read the figures out of Bitwise's page for its NEAR ETF (NRR).

Bitwise's terms limit copying site content, so only these figures leave this module, never the page. It raises if an
expected field disappears, so a redesign fails loudly instead of quietly producing empty tables.

The page has had two layouts, and both are read into the same figures:
- At nrretf.com, until 2026-11-16, it embedded its data as JSON in a `__NEXT_DATA__` script tag.
- From 2026-11-17 nrretf.com redirects to www.bitwiseetfs.com/single-asset/nrr. That page streams its data as React
  Server Component chunks (`self.__next_f.push([1, "..."])`), and the fund's figures sit in one object under the key
  `aggregate`, with the same fields under new section names. It carries no page-wide timestamp, so `page_updated_at`
  is null for it; nothing reads that field.

The page also shows a few figures for the current day only: the premium or discount to NAV, how many days the fund has
traded at each, and the 30-day median bid-ask spread. They are extras. One that is missing is saved as null, so a small
change to the page cannot cost the night's share count; the fetcher reports it as a warning.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)
_FLIGHT_CHUNK = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', re.S)
_AGGREGATE = re.compile(r'"aggregate":\s*(?=\{"ticker":"NRR")')

# Saved name: (section of the page's data, field), as the nrretf.com layout had them. Rates are fractions, as the page
# gives them: -0.0025 is a 0.25% discount. The three day counts are objects keyed by period, such as
# {"q4y2026": 18, "y2026": 18}.
EXTRAS = {
    "premium_discount_rate": ("premiumDiscount", "premiumDiscount"),
    "days_at_premium": ("premiumDiscount", "daysTradedAtPremium"),
    "days_at_discount": ("premiumDiscount", "daysTradedAtDiscount"),
    "days_at_nav": ("premiumDiscount", "daysTradedAtNav"),
    "bid_ask_spread_30d_median_rate": ("navAndMarketPrice", "thirtyDayMedianBidAskSpread"),
    "bid_ask_spread_as_of": ("navAndMarketPrice", "asOfDateMedianBidAskSpread"),
}


def _days(counts: Any) -> Optional[Dict[str, Any]]:
    """The bitwiseetfs.com layout lists the day counts as [{"label": "q4y2026", "value": 22}, ...]; keep the old shape."""
    if isinstance(counts, list):
        return {c["label"]: c["value"] for c in counts}
    return counts


def _spread(details: Dict[str, Any]) -> Dict[str, Any]:
    return details.get("thirtyDayMedianBidAskSpread") or {}


# The same extras in the bitwiseetfs.com layout, read from its `aggregate` object.
_AGGREGATE_EXTRAS: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    "premium_discount_rate": lambda a: (a["premiumDiscount"].get("difference") or {}).get("percent"),
    "days_at_premium": lambda a: _days(a["premiumDiscount"].get("daysTradedAtPremium")),
    "days_at_discount": lambda a: _days(a["premiumDiscount"].get("daysTradedAtDiscount")),
    "days_at_nav": lambda a: _days(a["premiumDiscount"].get("daysTradedAtNav")),
    "bid_ask_spread_30d_median_rate": lambda a: _spread(a["details"]).get("value"),
    "bid_ask_spread_as_of": lambda a: _spread(a["details"]).get("asOfDate"),
}
assert set(_AGGREGATE_EXTRAS) == set(EXTRAS)


def _chart(points: List[Any]) -> List[Dict[str, Any]]:
    """Points are [milliseconds, value] in the nrretf.com layout and {"t": milliseconds, "v": value} in the
    bitwiseetfs.com one. The page's values carry floating-point noise, such as 27.829999999999995.
    A day the chart has not filled yet has a null value: on 2026-11-09 the market price for 2026-11-05 was null while its
    NAV was there. That day is left out, not read as a redesign; a chart with no values at all still fails."""
    pairs = [(p["t"], p["v"]) if isinstance(p, dict) else (p[0], p[1]) for p in points]
    return [{"day": datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat(), "value": round(value, 2)}
            for ms, value in pairs if value is not None]


def _from_next_data(document: Dict[str, Any]) -> Dict[str, Any]:
    data = document["props"]["pageProps"]["fundData"]["data"]
    details, holdings, premium = data["fundDetails"], data["holdings"], data["premiumDiscount"]
    chart, wallets, staking = data["navAndMarketPrice"]["chart"], data["wallets"], data["fundDetails"]["stakingMetrics"]
    holding = holdings["basket"][0]
    parsed = _figures(details, holdings["asOfDate"], holding.get("companyName"), holding["shares"], staking, premium,
                      chart, wallets, data["updatedAt"])
    for name, (section, field) in EXTRAS.items():
        parsed[name] = data[section].get(field)
    return parsed


def _from_aggregate(aggregate: Dict[str, Any]) -> Dict[str, Any]:
    holding = aggregate["holdings"]["basket"][0]
    parsed = _figures(aggregate["details"], aggregate["holdings"]["asOfDate"], holding.get("name"), holding["assetInTrust"],
                      aggregate["staking"], aggregate["premiumDiscount"], aggregate["navMarketPrice"]["chart"],
                      aggregate["wallets"], None)
    for name, read in _AGGREGATE_EXTRAS.items():
        parsed[name] = read(aggregate)
    return parsed


def _figures(details, holdings_as_of, holding_name, near_in_trust, staking, premium, chart, wallets, page_updated_at):
    """The saved figures, the same for both layouts; `holding_name` is checked and dropped by parse()."""
    return {
        "as_of": details["asOfDate"],
        "shares_outstanding": details["sharesOutstanding"],
        "net_assets_usd": details["netAssets"],
        "near_in_trust": near_in_trust,
        "near_in_trust_as_of": holdings_as_of,
        "holding_name": holding_name,
        "gross_staking_rate": staking["grossStakingRewardRate"],
        "net_staking_rate": staking["netStakingRewardRate"],
        "staked_share": staking["currentPercentageOfAssetsStaked"],
        "staking_as_of": staking["asOfDate"],
        "premium_as_of": premium["asOfDate"],
        "volume_shares": premium["volume"],
        "nav_chart": _chart(chart["nav"]),
        "market_price_chart": _chart(chart["marketPrice"]),
        "wallets": [{"address": w["address"], "balance": w["balance"], "active": w["active"]} for w in wallets["walletBalances"]],
        "wallets_updated_at": wallets["updatedAt"],
        "page_updated_at": page_updated_at,
    }


def _aggregate_in_flight(html: str) -> Optional[Dict[str, Any]]:
    """The fund's `aggregate` object from the page's React Server Component chunks, or None if the page has none."""
    chunks = []
    for chunk in _FLIGHT_CHUNK.findall(html):
        try:
            chunks.append(json.loads(f'"{chunk}"'))
        except ValueError:
            continue
    flight = "".join(chunks)
    found = _AGGREGATE.search(flight)
    if not found:
        return None
    aggregate, _ = json.JSONDecoder().raw_decode(flight, found.end())
    return aggregate


def parse(html: str) -> Dict[str, Any]:
    next_data = _NEXT_DATA.search(html)
    try:
        if next_data:
            parsed = _from_next_data(json.loads(next_data.group(1)))
        else:
            aggregate = _aggregate_in_flight(html)
            if aggregate is None:
                raise ValueError("NRR page: no __NEXT_DATA__ script found, and no fund data in the page's chunks")
            parsed = _from_aggregate(aggregate)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        if str(e).startswith("NRR page:"):
            raise
        raise ValueError(f"NRR page: an expected field is missing or malformed: {e!r}") from e
    holding_name = parsed.pop("holding_name")
    if holding_name != "NEAR":
        raise ValueError(f"NRR page: expected the holding to be NEAR, found {holding_name!r}")
    for name in ("shares_outstanding", "near_in_trust", "nav_chart", "market_price_chart", "wallets"):
        if not parsed[name]:
            raise ValueError(f"NRR page: {name} is empty")
    return parsed
