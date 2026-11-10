"""Read the figures out of Bitwise's page for its NEAR ETF (NRR).

The page embeds its data as JSON in a `__NEXT_DATA__` script tag. Bitwise's terms limit copying site content, so only
these figures leave this module, never the page. It raises if an expected field disappears, so a redesign fails loudly
instead of quietly producing empty tables.

The page also shows a few figures for the current day only: the premium or discount to NAV, how many days the fund has
traded at each, and the 30-day median bid-ask spread. They are extras. One that is missing is saved as null, so a small
change to the page cannot cost the night's share count; the fetcher reports it as a warning.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

# Saved name: (section of the page's data, field). Rates are fractions, as the page gives them: -0.0025 is a 0.25% discount.
# The three day counts are objects keyed by period, such as {"q4y2026": 18, "y2026": 18}.
EXTRAS = {
    "premium_discount_rate": ("premiumDiscount", "premiumDiscount"),
    "days_at_premium": ("premiumDiscount", "daysTradedAtPremium"),
    "days_at_discount": ("premiumDiscount", "daysTradedAtDiscount"),
    "days_at_nav": ("premiumDiscount", "daysTradedAtNav"),
    "bid_ask_spread_30d_median_rate": ("navAndMarketPrice", "thirtyDayMedianBidAskSpread"),
    "bid_ask_spread_as_of": ("navAndMarketPrice", "asOfDateMedianBidAskSpread"),
}


def _chart(points: List[List[float]]) -> List[Dict[str, Any]]:
    """Points are [milliseconds, value]. The page's values carry floating-point noise, such as 27.829999999999995.
    A day the chart has not filled yet has a null value: on 2026-11-09 the market price for 2026-11-05 was null while its
    NAV was there. That day is left out, not read as a redesign; a chart with no values at all still fails."""
    return [{"day": datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat(), "value": round(value, 2)}
            for ms, value in points if value is not None]


def parse(html: str) -> Dict[str, Any]:
    found = _NEXT_DATA.search(html)
    if not found:
        raise ValueError("NRR page: no __NEXT_DATA__ script found")
    try:
        data = json.loads(found.group(1))["props"]["pageProps"]["fundData"]["data"]
        details, holdings, premium = data["fundDetails"], data["holdings"], data["premiumDiscount"]
        chart, wallets, staking = data["navAndMarketPrice"]["chart"], data["wallets"], data["fundDetails"]["stakingMetrics"]
        holding = holdings["basket"][0]
        parsed = {
            "as_of": details["asOfDate"],
            "shares_outstanding": details["sharesOutstanding"],
            "net_assets_usd": details["netAssets"],
            "near_in_trust": holding["shares"],
            "near_in_trust_as_of": holdings["asOfDate"],
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
            "page_updated_at": data["updatedAt"],
        }
        for name, (section, field) in EXTRAS.items():
            parsed[name] = data[section].get(field)
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ValueError(f"NRR page: an expected field is missing or malformed: {e!r}") from e
    if holding.get("companyName") != "NEAR":
        raise ValueError(f"NRR page: expected the holding to be NEAR, found {holding.get('companyName')!r}")
    for name in ("shares_outstanding", "near_in_trust", "nav_chart", "market_price_chart", "wallets"):
        if not parsed[name]:
            raise ValueError(f"NRR page: {name} is empty")
    return parsed
