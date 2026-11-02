"""Importing this package registers every dataset with the pipeline, and datasets run in this order.
rpc comes before neardata, because the block sampler reads the heights that rpc/block_day finds."""
from . import defi, defillama, dune, ecosystem, fastnear, intents, market, nearblocks, rpc, neardata  # noqa: F401
