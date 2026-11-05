"""Importing this package registers every dataset with the pipeline, and datasets run in this order.
rpc comes before lockups, etf and neardata, because they read the heights that rpc/block_day finds."""
from . import defi, defillama, dune, ecosystem, fastnear, intents, market, nearblocks, rpc, lockups, etf, neardata  # noqa: F401
