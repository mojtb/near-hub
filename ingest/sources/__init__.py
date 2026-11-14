"""Importing this package registers every dataset with the pipeline, and datasets run in this order.
rpc comes before lockups, etf and neardata, because they read the heights that rpc/block_day finds, and after
fastnear, because rpc/ft_metadata reads the tokens fastnear finds. intents_pool comes last, because it reads those
heights and the token list intents saves. bigquery reads nothing the others save, and is skipped without a Google key."""
from . import defi, defillama, dune, ecosystem, fastnear, intents, market, nearblocks, rpc, lockups, etf, neardata, intents_pool, bigquery  # noqa: F401
