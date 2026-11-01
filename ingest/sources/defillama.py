"""DefiLlama: chain and protocol TVL, fees, revenue, DEX volume, stablecoins. No key.

Very large responses (/protocols, /protocol/<slug>, /pools) are trimmed to NEAR before saving
and the manifest note says so; everything else is stored exactly as received.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import List

from ..http import HttpError
from ..pipeline import Context, dataset
from ..settings import read_registry
from ._common import OVERLAP_DAYS, fetch, has_prior

SOURCE = "defillama"
API = "https://api.llama.fi"
COINS = "https://coins.llama.fi"
STABLES = "https://stablecoins.llama.fi"
YIELDS = "https://yields.llama.fi"
TOP_NEAR_PROTOCOLS = 25
PRICE_HISTORY_START = date(2020, 9, 1)
PRICE_POINTS_PER_CALL = 450
INTENTS_FEE_TYPES = ["dailyFees", "dailyRevenue", "dailyHoldersRevenue", "dailyProtocolRevenue", "dailySupplySideRevenue"]


def _peer_chains() -> List[str]:
    return [p["llama_chain"] for p in read_registry("peers")]


@dataset(SOURCE, "chains")
def chains(ctx: Context) -> None:
    fetch(ctx, SOURCE, "chains", "all", f"{API}/v2/chains")


@dataset(SOURCE, "chain_tvl")
def chain_tvl(ctx: Context) -> None:
    for chain in _peer_chains():
        fetch(ctx, SOURCE, "chain_tvl", chain, f"{API}/v2/historicalChainTvl/{chain}")


@dataset(SOURCE, "chain_fees")
def chain_fees(ctx: Context) -> None:
    for chain in _peer_chains():
        for data_type in ("dailyFees", "dailyRevenue"):
            params = {"excludeTotalDataChartBreakdown": "true", "dataType": data_type}
            fetch(ctx, SOURCE, "chain_fees", f"{chain}__{data_type}", f"{API}/overview/fees/{chain}", params=params)


@dataset(SOURCE, "chain_dex_volume")
def chain_dex_volume(ctx: Context) -> None:
    for chain in _peer_chains():
        params = {"excludeTotalDataChartBreakdown": "true"}
        fetch(ctx, SOURCE, "chain_dex_volume", chain, f"{API}/overview/dexs/{chain}", params=params)


@dataset(SOURCE, "intents_volume")
def intents_volume(ctx: Context) -> None:
    fetch(ctx, SOURCE, "intents_volume", "near-intents", f"{API}/summary/dexs/near-intents")


@dataset(SOURCE, "intents_fees")
def intents_fees(ctx: Context) -> None:
    for data_type in INTENTS_FEE_TYPES:
        fetch(ctx, SOURCE, "intents_fees", data_type, f"{API}/summary/fees/near-intents", params={"dataType": data_type})


@dataset(SOURCE, "protocols")
def protocols(ctx: Context) -> None:
    """Every protocol with TVL on NEAR, then the TVL history of the largest ones."""
    url = f"{API}/protocols"
    reply = ctx.http.get(url, timeout=240)
    rows = [p for p in reply.json() if "Near" in (p.get("chains") or [])]
    ctx.bronze.save_json(SOURCE, "protocols", "near", rows, url=url, rows=len(rows),
                         note="trimmed: only protocols listing Near in chains")
    rows.sort(key=lambda p: -((p.get("chainTvls") or {}).get("Near") or 0))
    for p in rows[:TOP_NEAR_PROTOCOLS]:
        slug = p["slug"]
        detail_url = f"{API}/protocol/{slug}"
        try:
            detail = ctx.http.get(detail_url, timeout=240).json()
        except HttpError as e:
            ctx.warn(f"{slug}: {e}")
            continue
        near = (detail.get("chainTvls") or {}).get("Near") or {}
        keep = {k: detail.get(k) for k in ("id", "name", "slug", "category", "url", "chains", "parentProtocol", "audits", "description")}
        keep["near_tvl"] = near.get("tvl") or []
        ctx.bronze.save_json(SOURCE, "protocol_tvl", slug, keep, url=detail_url, rows=len(keep["near_tvl"]),
                             note="trimmed: metadata plus the chainTvls.Near.tvl series")


@dataset(SOURCE, "stablecoin_chain")
def stablecoin_chain(ctx: Context) -> None:
    for chain in _peer_chains():
        fetch(ctx, SOURCE, "stablecoin_chain", chain, f"{STABLES}/stablecoincharts/{chain}")


@dataset(SOURCE, "stablecoin_assets")
def stablecoin_assets(ctx: Context) -> None:
    """Point-in-time supply per stablecoin per chain, trimmed to the peer chains."""
    url = f"{STABLES}/stablecoins"
    reply = ctx.http.get(url, params={"includePrices": "false"}, timeout=180)
    wanted = set(_peer_chains())
    rows = []
    for asset in reply.json().get("peggedAssets", []):
        circulating = {c: v for c, v in (asset.get("chainCirculating") or {}).items() if c in wanted}
        if circulating:
            rows.append({"id": asset.get("id"), "name": asset.get("name"), "symbol": asset.get("symbol"),
                         "pegType": asset.get("pegType"), "chainCirculating": circulating})
    ctx.bronze.save_json(SOURCE, "stablecoin_assets", "peers", rows, url=url, rows=len(rows),
                         note="trimmed: chainCirculating limited to peer chains")


@dataset(SOURCE, "peer_price")
def peer_price(ctx: Context) -> None:
    """Daily prices per peer. Asking from a midnight start returns points stamped exactly 00:00 UTC."""
    today = date.fromisoformat(ctx.snapshot)
    midnight = lambda d: int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
    for peer in read_registry("peers"):
        key = peer["coingecko_id"]  # DefiLlama's own coin key is "coingecko:<id>"; no CoinGecko call is made
        url = f"{COINS}/chart/coingecko:{key}"
        if has_prior(ctx, SOURCE, "peer_price", f"{key}__recent"):
            fetch(ctx, SOURCE, "peer_price", f"{key}__recent", url,
                  params={"start": midnight(today - timedelta(days=OVERLAP_DAYS)), "span": OVERLAP_DAYS + 1, "period": "1d"})
            continue
        start = PRICE_HISTORY_START
        while start < today:
            fetch(ctx, SOURCE, "peer_price", f"{key}__{start.isoformat()}", url,
                  params={"start": midnight(start), "span": PRICE_POINTS_PER_CALL, "period": "1d"})
            start += timedelta(days=PRICE_POINTS_PER_CALL)
        fetch(ctx, SOURCE, "peer_price", f"{key}__recent", url,
              params={"start": midnight(today - timedelta(days=OVERLAP_DAYS)), "span": OVERLAP_DAYS + 1, "period": "1d"})


@dataset(SOURCE, "yield_pools")
def yield_pools(ctx: Context) -> None:
    url = f"{YIELDS}/pools"
    reply = ctx.http.get(url, timeout=240)
    rows = [p for p in reply.json().get("data", []) if p.get("chain") == "Near"]
    ctx.bronze.save(SOURCE, "yield_pools", "near", json.dumps(rows).encode(), url=url, rows=len(rows),
                    note="trimmed: only pools with chain Near")
