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
# The NEAR Intents pool's balances are read from the chain at month ends from 2024-11, so token prices start here.
TOKEN_PRICE_HISTORY_START = date(2024, 11, 1)
# DefiLlama also serves dailyHoldersRevenue, dailyProtocolRevenue and dailySupplySideRevenue for near-intents. They are
# arithmetic of these two (revenue split at 2026-02-23, and fees minus revenue), so they are not fetched; bronze up to
# 2026-11-08 holds them.
INTENTS_FEE_TYPES = ["dailyFees", "dailyRevenue"]


def _peer_chains() -> List[str]:
    return [p["llama_chain"] for p in read_registry("peers")]


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


@dataset(SOURCE, "chain_gas_fees")
def chain_gas_fees(ctx: Context) -> None:
    """Fees paid to each chain itself, from the chain's own adapter. /overview/fees/<chain> leaves them out: it sums the
    applications on the chain (checked 2026-11-10: NEAR's 30-day total there is its protocol rows without the Near row)."""
    for chain in _peer_chains():
        # The chain adapter's slug is the chain's name in lower case for all seven peers, checked 2026-11-10. The same
        # route serves protocols, so a reply that is not a chain's own adapter is refused, not saved.
        url, params = f"{API}/summary/fees/{chain.lower()}", {"dataType": "dailyFees"}
        try:
            reply = ctx.http.get(url, params=params)
        except HttpError as e:
            ctx.warn(f"{chain}: {e}")
            continue
        if reply.json().get("protocolType") != "chain":
            ctx.warn(f"{chain}: {url} is not a chain's own adapter, so it was not saved")
            continue
        ctx.bronze.save(SOURCE, "chain_gas_fees", chain, reply.content, url=url, params=params, status=reply.status)


@dataset(SOURCE, "chain_dex_volume")
def chain_dex_volume(ctx: Context) -> None:
    for chain in _peer_chains():
        params = {"excludeTotalDataChartBreakdown": "true"}
        fetch(ctx, SOURCE, "chain_dex_volume", chain, f"{API}/overview/dexs/{chain}", params=params)


@dataset(SOURCE, "intents_volume")
def intents_volume(ctx: Context) -> None:
    fetch(ctx, SOURCE, "intents_volume", "near-intents", f"{API}/summary/dexs/near-intents")


@dataset(SOURCE, "swap_service_volume")
def swap_service_volume(ctx: Context) -> None:
    """Daily volume of the other cross-chain swap services in registry/swap_services.csv, each from the DefiLlama list its
    row names. `dexs` holds the swaps a service settled, the list NEAR Intents itself is in. `bridges` holds what was sent
    into a service on one chain to arrive on another: dailyOutgoingVolume counts each transfer once, where the per-chain
    breakdown counts it leaving and arriving (checked 2026-11-12 on Across: the breakdown sums to twice the total).
    NEAR Intents' own row names no list, because its series is fct_intents_daily's."""
    for service in read_registry("swap_services"):
        dimension, slug = service["llama_dimension"], service["llama_slug"]
        if not slug:
            continue
        url = f"{API}/summary/{dimension}/{slug}"
        params = {"excludeTotalDataChartBreakdown": "true", "dataType": service["llama_data_type"]}
        try:
            reply = ctx.http.get(url, params=params)
        except HttpError as e:
            ctx.warn(f"{slug}: {e}")
            continue
        # A slug can pass to another listing while the id stays (Templar, 2026-11-05), so the reply must carry the
        # registry's id. A reply for anything else is refused, not saved under this service's name.
        answered = str(reply.json().get("defillamaId"))
        if answered != service["llama_id"]:
            ctx.warn(f"{slug}: {url} answered for id {answered}, not {service['llama_id']}, so it was not saved")
            continue
        ctx.bronze.save(SOURCE, "swap_service_volume", f"{dimension}__{slug}", reply.content, url=url, params=params,
                        status=reply.status)


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


@dataset(SOURCE, "token_price")
def token_price(ctx: Context) -> None:
    """Daily price of each asset in registry/token_prices.csv that DefiLlama prices, asked like peer_price.

    The registry gives DefiLlama's own coin key: `coingecko:<id>`, or `<chain>:<address>` for a token contract. No
    CoinGecko call is made. A window before a coin's first price comes back empty and is saved as the answer it is. The
    warehouse finds a coin by the key in the reply, so a reply that names the coin by another key than the registry's,
    in another case for instance, is refused with a warning that shows the key DefiLlama uses."""
    today = date.fromisoformat(ctx.snapshot)
    midnight = lambda d: int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
    for token in read_registry("token_prices"):
        if token["price_source"] != "defillama":
            continue
        coin = token["source_asset_id"]
        url = f"{COINS}/chart/{coin}"
        windows = [(f"{coin}__recent", {"start": midnight(today - timedelta(days=OVERLAP_DAYS)), "span": OVERLAP_DAYS + 1, "period": "1d"})]
        if not has_prior(ctx, SOURCE, "token_price", f"{coin}__recent"):
            start = TOKEN_PRICE_HISTORY_START
            while start < today:
                windows.insert(-1, (f"{coin}__{start.isoformat()}", {"start": midnight(start), "span": PRICE_POINTS_PER_CALL, "period": "1d"}))
                start += timedelta(days=PRICE_POINTS_PER_CALL)
        for key, params in windows:
            try:
                reply = ctx.http.get(url, params=params)
            except HttpError as e:
                ctx.warn(f"{key}: {e}")
                continue
            answered = sorted(reply.json().get("coins") or {})
            if answered not in ([], [coin]):
                ctx.warn(f"{key}: {url} answered for {answered}, not {coin}, so it was not saved")
                continue
            ctx.bronze.save(SOURCE, "token_price", key, reply.content, url=url, params=params, status=reply.status)


@dataset(SOURCE, "yield_pools")
def yield_pools(ctx: Context) -> None:
    url = f"{YIELDS}/pools"
    reply = ctx.http.get(url, timeout=240)
    rows = [p for p in reply.json().get("data", []) if p.get("chain") == "Near"]
    ctx.bronze.save(SOURCE, "yield_pools", "near", json.dumps(rows).encode(), url=url, rows=len(rows),
                    note="trimmed: only pools with chain Near")
