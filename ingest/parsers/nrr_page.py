"""Read the figures out of Bitwise's page for its NEAR ETF (NRR).

The page embeds its data as JSON in a `__NEXT_DATA__` script tag. Bitwise's terms limit copying site content, so only
these figures leave this module, never the page. It raises if an expected field disappears, so a redesign fails loudly
instead of quietly producing empty tables.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def _chart(points: List[List[float]]) -> List[Dict[str, Any]]:
    """Points are [milliseconds, value]. The page's values carry floating-point noise, such as 27.829999999999995."""
    return [{"day": datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date().isoformat(), "value": round(value, 2)} for ms, value in points]


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
    except (KeyError, IndexError, TypeError, ValueError) as e:
        raise ValueError(f"NRR page: an expected field is missing or malformed: {e!r}") from e
    if holding.get("companyName") != "NEAR":
        raise ValueError(f"NRR page: expected the holding to be NEAR, found {holding.get('companyName')!r}")
    for name in ("shares_outstanding", "near_in_trust", "nav_chart", "market_price_chart", "wallets"):
        if not parsed[name]:
            raise ValueError(f"NRR page: {name} is empty")
    return parsed
