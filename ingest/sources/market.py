"""Prices and market caps for NEAR and its peers. No keys needed.

Coinbase gives exchange candles for NEAR, and CoinMetrics community gives a reference rate and
market cap with full history. DefiLlama's price API, in defillama.py, is the third price source.

Deliberately not used: CoinGecko and GeckoTerminal, whose API terms do not allow storing or
republishing data, which a reproducible public repository has to do. Binance answers 451 from
some locations, including this project's build machine.
"""
from __future__ import annotations

from datetime import date, timedelta

from ..pipeline import Context, dataset
from ..settings import read_registry
from ._common import OVERLAP_DAYS, fetch, has_prior

COINBASE = "https://api.exchange.coinbase.com"
COINMETRICS = "https://community-api.coinmetrics.io/v4"
CANDLES_PER_CALL = 300
COINBASE_FIRST_DAY = date(2022, 9, 1)  # NEAR-USD began trading around 2022-09; earlier calls return nothing


@dataset("coinbase", "candles")
def coinbase_candles(ctx: Context) -> None:
    """Daily OHLCV for NEAR-USD. Each row is [time, low, high, open, close, volume]."""
    today = date.fromisoformat(ctx.snapshot)
    start = today - timedelta(days=OVERLAP_DAYS) if has_prior(ctx, "coinbase", "candles") else COINBASE_FIRST_DAY
    while start < today:
        end = min(start + timedelta(days=CANDLES_PER_CALL - 1), today)
        params = {"granularity": 86400, "start": start.isoformat(), "end": end.isoformat()}
        fetch(ctx, "coinbase", "candles", f"near_usd_{start.isoformat()}", f"{COINBASE}/products/NEAR-USD/candles", params=params)
        start = end


@dataset("coinmetrics", "asset_metrics")
def coinmetrics_asset_metrics(ctx: Context) -> None:
    """Community metrics per peer asset. Follows next_page_url until the series ends."""
    today = date.fromisoformat(ctx.snapshot)
    for peer in read_registry("peers"):
        asset = peer["coinmetrics_asset"]
        if not asset:
            continue
        # Decided per asset, so one added or renamed later still gets its whole history on its first read: TON's id
        # changed from `ton`, which now returns nothing, to `gram`.
        first_run = not has_prior(ctx, "coinmetrics", "asset_metrics", asset)
        start = "2020-01-01" if first_run else (today - timedelta(days=OVERLAP_DAYS)).isoformat()
        url = f"{COINMETRICS}/timeseries/asset-metrics"
        params = {"assets": asset, "metrics": "PriceUSD,CapMrktEstUSD,volume_reported_spot_usd_1d", "frequency": "1d",
                  "start_time": start, "page_size": 10000, "paging_from": "start", "ignore_forbidden_errors": "true",
                  "ignore_unsupported_errors": "true"}
        fetch(ctx, "coinmetrics", "asset_metrics", asset, url, params=params)
