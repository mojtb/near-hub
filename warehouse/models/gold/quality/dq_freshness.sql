-- How current each dataset is, relative to the newest snapshot the build can see, and whether that is too old.
-- A daily dataset is measured by its newest day of data, a snapshot dataset by its newest read. Each carries the most
-- days it may fall behind; past that it is stale and the test no_dataset_is_stale fails, so a source that stops arriving
-- turns the build red instead of going quiet. The limits leave room for one missed night. No limit means the dataset is
-- not expected to keep up: a reading taken by hand, or a source that is being switched off.
{% set daily = [
    ('stg_nearblocks__charts_v1', 'NearBlocks legacy daily charts, switched off on 2026-11-22', none),
    ('stg_nearblocks__block_stats', 'NearBlocks daily blocks, gas and supply', 3),
    ('stg_nearblocks__price_stats', 'NearBlocks daily price', 3),
    ('stg_nearblocks__txn_stats', 'NearBlocks daily transactions', 3),
    ('stg_nearblocks__address_stats', 'NearBlocks daily accounts', 3),
    ('stg_nearblocks__intents_daily', 'NearBlocks Intents daily', 3),
    ('stg_nearblocks__intents_volume_by_chain', 'NearBlocks Intents by chain', 3),
    ('stg_nearblocks__intents_volume_by_asset', 'NearBlocks Intents by asset', 3),
    ('stg_nearblocks__signer_stats', 'NearBlocks v1.signer daily', 3),
    ('fct_dune_intents_asset_daily', 'Dune dashboard Intents by asset, read by hand', none),
    ('stg_intents_explorer__days', 'Intents Explorer daily tally', 3),
    ('stg_rpc__contract_views_history', 'Contract views replayed by day: liquid staking, veNEAR, MPC', 3),
    ('stg_nearblocks__contract_txns', 'NearBlocks per-contract daily', 3),
    ('stg_nearblocks__wallet_balance', 'NearBlocks wallet balances', 3),
    ('stg_defillama__intents_volume', 'DefiLlama Intents volume', 3),
    ('stg_defillama__intents_fees', 'DefiLlama Intents fees', 3),
    ('stg_defillama__chain_tvl', 'DefiLlama chain TVL', 3),
    ('stg_defillama__chain_fees', 'DefiLlama chain fees', 3),
    ('stg_defillama__chain_gas_fees', 'DefiLlama chain gas fees', 3),
    ('stg_defillama__chain_dex_volume', 'DefiLlama DEX volume', 3),
    ('stg_defillama__protocol_tvl', 'DefiLlama protocol TVL', 3),
    ('stg_defillama__stablecoin_chain', 'DefiLlama stablecoins', 3),
    ('stg_revenue_page__fees_daily', 'revenue.near.org fees', 3),
    ('stg_revenue_page__volume_daily', 'revenue.near.org volume', 3),
    ('stg_revenue_page__confidential_tvl', 'revenue.near.org confidential TVL', 3),
    ('stg_revenue_page__revenue_vs_emissions', 'revenue.near.org revenue and emissions', 3),
    ('stg_coinbase__candles', 'Coinbase candles', 3),
    ('stg_coinmetrics__asset_metrics', 'CoinMetrics', 3),
    ('stg_defillama__peer_price', 'DefiLlama prices', 3),
    ('stg_rpc__block_day', 'Archival RPC daily block', 3),
    ('stg_rpc__lockup_foundation_balances', 'Foundation lockup balances on chain', 3),
    ('stg_fastnear__transfers', 'FastNear wallet transfers', 3),
    ('stg_neardata__receiver_sample', 'Neardata receiver sample', 3),
    ('stg_nrr_fund__prices', 'Bitwise NEAR ETF NAV and market price', 7),
    ('stg_nrr_fund__readings', 'Bitwise NEAR ETF fund readings', 7),
    ('stg_rpc__nrr_pool_daily', 'Bitwise NEAR ETF wallets on chain', 3)
] %}
{# The fund trades on weekdays and fills its chart a day late, so a Monday read is four days behind and a holiday adds more. #}
{% set snapshots = [
    ('stg_rpc__validators', 'Validator set'),
    ('stg_rpc__protocol_config', 'Protocol config'),
    ('stg_rpc__accounts', 'Registry accounts on chain'),
    ('stg_rpc__contract_views', 'Contract views: MPC, liquid staking, veNEAR'),
    ('stg_rpc__hos_proposals', 'House of Stake proposals'),
    ('stg_rpc__lockup_contract_views', 'Lockup contracts on chain'),
    ('stg_fastnear__holdings', 'FastNear wallet holdings'),
    ('stg_fastnear__ft_top_holders', 'FastNear token holders'),
    ('stg_oneclick__tokens', '1Click token list'),
    ('stg_rhea__token_prices', 'Rhea token prices'),
    ('stg_defillama__protocols', 'DefiLlama protocol list'),
    ('stg_defillama__chain_fee_protocols', 'DefiLlama fees by protocol'),
    ('stg_defillama__stablecoin_assets', 'DefiLlama stablecoins by asset'),
    ('stg_defillama__yield_pools', 'DefiLlama yield pools'),
    ('stg_nearblocks__mpc_operators', 'NearBlocks MPC operators'),
    ('stg_revenue_page__capture_rates', 'revenue.near.org capture rates'),
    ('stg_revenue_page__revenue_monthly', 'revenue.near.org monthly revenue'),
    ('stg_github__repos', 'GitHub repositories'),
    ('stg_github__weekly_commits_list', 'GitHub commits on the default branch'),
    ('stg_gov__topics', 'Governance forum threads'),
    ('stg_nearcatalog__projects', 'NEAR Catalog projects')
] %}

with readings as (
    {% for model, label, limit in daily %}
    select '{{ model }}' as model, '{{ label }}' as dataset, 'daily' as cadence,
        max(snapshot_date) as latest_snapshot, max(date_day) as latest_data_day, count(*) as rows_all_snapshots,
        cast({{ limit if limit is not none else 'null' }} as integer) as max_days_behind
    from {{ ref(model) }}
    union all
    {% endfor %}
    {% for model, label in snapshots %}
    select '{{ model }}' as model, '{{ label }}' as dataset, 'snapshot' as cadence,
        max(snapshot_date) as latest_snapshot, max(snapshot_date) as latest_data_day, count(*) as rows_all_snapshots,
        2 as max_days_behind
    from {{ ref(model) }}
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
),

newest as (select max(latest_snapshot) as as_of from readings)

select
    r.dataset,
    r.model,
    r.cadence,
    r.latest_snapshot,
    r.latest_data_day,
    newest.as_of,
    date_diff('day', r.latest_data_day, newest.as_of) as days_behind,
    r.max_days_behind,
    coalesce(date_diff('day', r.latest_data_day, newest.as_of) > r.max_days_behind, false) as is_stale,
    r.rows_all_snapshots
from readings r, newest
