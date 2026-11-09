"""Protocol APIs on NEAR: Rhea (formerly Ref). No keys.

Meta Pool's Prometheus metrics were fetched here until 2026-11-10. Nothing read them: stNEAR's price, supply and staked
NEAR come from the contract itself, in rpc.py. The nights already fetched stay in bronze."""
from __future__ import annotations

from ..pipeline import Context, dataset
from ._common import fetch

REF_API = "https://api.ref.finance"
REF_INDEXER = "https://indexer.ref.finance"


@dataset("rhea", "top_pools")
def rhea_top_pools(ctx: Context) -> None:
    fetch(ctx, "rhea", "top_pools", "all", f"{REF_API}/list-top-pools", timeout=180)


@dataset("rhea", "token_prices")
def rhea_token_prices(ctx: Context) -> None:
    fetch(ctx, "rhea", "token_prices", "all", f"{REF_INDEXER}/list-token-price", timeout=180)

