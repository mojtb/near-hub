"""One-off: bring the 2026-10-28 snapshot from the earlier near-deflation-clock scaffold into bronze.

It gives the warehouse an older point-in-time reading of wallets, validators and MPC state, plus a
first baseline for detecting restated history. That scaffold re-serialised its JSON, so these files
are the same data but not the same bytes the servers sent; each manifest note records this.

Usage: python -m tools.import_legacy_snapshot <path to data/raw/2026-10-28>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ingest.bronze import BronzeWriter
from ingest.sources.rpc import _trim_validators

NOTE = "imported from the near-deflation-clock scaffold (re-serialised JSON, original fetch time {fetched_at})"

# legacy file stem -> (source, dataset, key)
SAME_SHAPE = {
    "defillama_chain_tvl_near": ("defillama", "chain_tvl", "Near"),
    "defillama_dexs_near_intents": ("defillama", "intents_volume", "near-intents"),
    "defillama_fees_near_intents_dailyFees": ("defillama", "intents_fees", "dailyFees"),
    "defillama_fees_near_intents_dailyRevenue": ("defillama", "intents_fees", "dailyRevenue"),
    "defillama_fees_near_intents_dailyHoldersRevenue": ("defillama", "intents_fees", "dailyHoldersRevenue"),
    "defillama_fees_near_intents_dailyProtocolRevenue": ("defillama", "intents_fees", "dailyProtocolRevenue"),
    "defillama_overview_dexs_near": ("defillama", "chain_dex_volume", "Near"),
    "defillama_overview_fees_near": ("defillama", "chain_fees", "Near__dailyFees"),
    "defillama_stablecoins_near": ("defillama", "stablecoin_chain", "Near"),
    "fastnear_account_buybacks_multisignature_near": ("fastnear", "account_full", "buybacks.multisignature.near"),
    "fastnear_account_fefundsadmin_sputnik-dao_near": ("fastnear", "account_full", "fefundsadmin.sputnik-dao.near"),
    "fastnear_account_1csfundsadmin_sputnik-dao_near": ("fastnear", "account_full", "1csfundsadmin.sputnik-dao.near"),
    "fastnear_account_intents_near": ("fastnear", "account_full", "intents.near"),
    "nearblocks_v1_charts": ("nearblocks", "charts_v1", "all"),
    "nearblocks_v1_stats": ("nearblocks", "stats_v1", "all"),
    "nearblocks_v3_stats": ("nearblocks", "stats", "all"),
    "nearblocks_v3_blocks_stats": ("nearblocks", "blocks_24h", "all"),
    "nearblocks_v3_txns_stats": ("nearblocks", "txns_24h", "all"),
    "nearblocks_v3_intents_stats": ("nearblocks", "intents_totals", "all"),
    "nearblocks_v3_txn_stats": ("nearblocks", "txn_stats", "all"),
    "nearblocks_v3_address_stats": ("nearblocks", "address_stats", "all"),
    "nearblocks_v3_tvl_stats": ("nearblocks", "tvl_stats", "all"),
    "nearblocks_v3_intents_volume_stats": ("nearblocks", "intents_volume", "all"),
    "nearblocks_v3_intents_swap_stats": ("nearblocks", "intents_swaps", "all"),
    "nearblocks_v3_intents_account_stats": ("nearblocks", "intents_accounts", "all"),
    "nearblocks_v3_intents_volume_by_chain": ("nearblocks", "intents_volume_by_chain", "all"),
    "nearblocks_v3_signer_v1_daily": ("nearblocks", "contract_txns", "v1.signer"),
    "nearblocks_v3_balance_buybacks_multisignature_near": ("nearblocks", "wallet_balance", "buybacks.multisignature.near"),
    "nearblocks_v3_balance_fefundsadmin_sputnik-dao_near": ("nearblocks", "wallet_balance", "fefundsadmin.sputnik-dao.near"),
    "rpc_status": ("rpc", "status", "all"),
    "rpc_gas_price": ("rpc", "gas_price", "latest"),
    "rpc_protocol_config": ("rpc", "protocol_config", "final"),
}


def main(folder: str) -> None:
    legacy = Path(folder)
    manifest = json.loads((legacy / "manifest.json").read_text())["files"]
    writer = BronzeWriter(legacy.name)

    def info(stem: str):
        entry = manifest[f"{stem}.json"]
        return entry["url"].split(" ")[0], NOTE.format(fetched_at=entry["fetched_at"])

    for stem, (source, dataset, key) in SAME_SHAPE.items():
        url, note = info(stem)
        writer.save(source, dataset, key, (legacy / f"{stem}.json").read_bytes(), url=url, note=note)

    url, note = info("rpc_validators")
    validators = json.loads((legacy / "rpc_validators.json").read_text())["result"]
    writer.save_json("rpc", "validators_current", "latest", _trim_validators(validators), url=url,
                     note=note + "; trimmed: per-shard arrays and public keys dropped")

    url, note = info("rpc_v1_signer_state")
    state = json.loads((legacy / "rpc_v1_signer_state.json").read_text())
    writer.save_json("rpc", "contract_views", "v1.signer__state",
                     {"block_height": None, "contract": "v1.signer", "method": "state", "args": {}, "result": state},
                     url=url, note=note)
    writer.flush()
    print(f"Imported {len(writer._entries)} files into bronze as dt={legacy.name}")


if __name__ == "__main__":
    main(sys.argv[1])
