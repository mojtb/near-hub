"""Protocol APIs on NEAR: Rhea (formerly Ref) and Meta Pool. No keys."""
from __future__ import annotations

from ..parsers.prometheus import parse as parse_prometheus
from ..pipeline import Context, dataset
from ._common import fetch

REF_API = "https://api.ref.finance"
REF_INDEXER = "https://indexer.ref.finance"
META_POOL_METRICS = "https://validators.narwallets.com/metrics"


@dataset("rhea", "top_pools")
def rhea_top_pools(ctx: Context) -> None:
    fetch(ctx, "rhea", "top_pools", "all", f"{REF_API}/list-top-pools", timeout=180)


@dataset("rhea", "token_prices")
def rhea_token_prices(ctx: Context) -> None:
    fetch(ctx, "rhea", "token_prices", "all", f"{REF_INDEXER}/list-token-price", timeout=180)


@dataset("metapool", "metrics")
def metapool_metrics(ctx: Context) -> None:
    reply = fetch(ctx, "metapool", "metrics", "prometheus", META_POOL_METRICS, ext="txt", timeout=90)
    if reply is not None:
        metrics = parse_prometheus(reply.content.decode("utf-8", "replace"))
        ctx.bronze.save_json("metapool", "metrics_parsed", "prometheus", metrics, url=META_POOL_METRICS,
                             note="derived from metrics/prometheus by ingest/parsers/prometheus.py")
