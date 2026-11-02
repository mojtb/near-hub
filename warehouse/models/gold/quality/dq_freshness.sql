-- How current each daily dataset is, relative to the newest snapshot the build can see.
{% set daily = [
    ('stg_nearblocks__charts_v1', 'NearBlocks legacy daily charts'),
    ('stg_nearblocks__txn_stats', 'NearBlocks daily transactions'),
    ('stg_nearblocks__address_stats', 'NearBlocks daily accounts'),
    ('stg_nearblocks__intents_daily', 'NearBlocks Intents daily'),
    ('stg_nearblocks__intents_volume_by_chain', 'NearBlocks Intents by chain'),
    ('stg_nearblocks__intents_volume_by_asset', 'NearBlocks Intents by asset'),
    ('fct_dune_intents_asset_daily', 'Dune dashboard Intents by asset, read by hand'),
    ('stg_intents_explorer__days', 'Intents Explorer daily tally'),
    ('stg_nearblocks__contract_txns', 'NearBlocks per-contract daily'),
    ('stg_nearblocks__wallet_balance', 'NearBlocks wallet balances'),
    ('stg_defillama__intents_volume', 'DefiLlama Intents volume'),
    ('stg_defillama__intents_fees', 'DefiLlama Intents fees'),
    ('stg_defillama__chain_tvl', 'DefiLlama chain TVL'),
    ('stg_defillama__chain_fees', 'DefiLlama chain fees'),
    ('stg_defillama__protocol_tvl', 'DefiLlama protocol TVL'),
    ('stg_defillama__stablecoin_chain', 'DefiLlama stablecoins'),
    ('stg_revenue_page__fees_daily', 'revenue.near.org fees'),
    ('stg_revenue_page__volume_daily', 'revenue.near.org volume'),
    ('stg_coinbase__candles', 'Coinbase candles'),
    ('stg_coinmetrics__asset_metrics', 'CoinMetrics'),
    ('stg_defillama__peer_price', 'DefiLlama prices'),
    ('stg_rpc__block_day', 'Archival RPC daily block'),
    ('stg_nrr_fund__prices', 'Bitwise NEAR ETF NAV and market price'),
    ('stg_rpc__nrr_pool_daily', 'Bitwise NEAR ETF wallets on chain')
] %}

with readings as (
    {% for model, label in daily %}
    select '{{ model }}' as model, '{{ label }}' as dataset, max(snapshot_date) as latest_snapshot, max(date_day) as latest_data_day, count(*) as rows_all_snapshots
    from {{ ref(model) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

newest as (select max(latest_snapshot) as as_of from readings)

select
    r.dataset,
    r.model,
    r.latest_snapshot,
    r.latest_data_day,
    newest.as_of,
    date_diff('day', r.latest_data_day, newest.as_of) as days_behind,
    r.rows_all_snapshots
from readings r, newest
