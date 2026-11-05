-- Every place two sources should tell the same story, side by side. `independence` matters: DefiLlama and
-- revenue.near.org both read NEAR's own Dune uploads, so their agreement proves little. NearBlocks, the wallet
-- transfers and the chain itself are independent checks. A gap beyond tolerance must have a written explanation
-- in registry/reconciliation_notes.csv, or `make verify` fails.
{% set as_of_days = 30 %}

with intents as (select * from {{ ref('fct_intents_daily') }}),

dune as (
    select metric, scope, value_usd from {{ ref('fct_intents_dashboard_readings') }}
    where snapshot_date = (select max(snapshot_date) from {{ ref('fct_intents_dashboard_readings') }})
),

-- A dashboard reading is taken by hand, so it stands still while the daily series move on. Its all-time tiles are
-- therefore compared with the other source on the reading's last full day, which is what the tiles covered.
dune_day as (
    select max(snapshot_date) - 1 as d from {{ ref('fct_intents_dashboard_readings') }}
),

market_latest_cm as (
    select * from {{ ref('fct_market_daily') }}
    where price_usd_coinmetrics is not null and market_cap_usd_coinmetrics is not null and circulating_supply_near_nearblocks is not null
    order by date_day desc limit 1
),

-- NearBlocks stopped computing circulating supply on this day, so it is the last day its figure can test the chain-built one.
nearblocks_last_live as (select date '2025-08-26' as d),

circulating_years as (
    select
        year(date_day) as y,
        avg(circulating_supply_near) as chain,
        avg(circulating_supply_near_nearblocks) as nearblocks
    from {{ ref('fct_supply_daily') }}, nearblocks_last_live
    where date_day <= d and circulating_supply_near is not null and circulating_supply_near_nearblocks is not null
    group by 1
),

published_supply as (select * from {{ ref('near_supply_readings') }} where reading = 'published_circulating_supply'),

latest_lockup_views as (
    select * from {{ ref('stg_rpc__lockup_contract_views') }}
    where read_day = (select max(read_day) from {{ ref('stg_rpc__lockup_contract_views') }}) and transfers_enabled
),

lockup_schedules as (
    select *, {{ lockup_dates() }} from {{ ref('stg_rpc__lockups') }} where is_latest and lockup_amount_near is not null
),

foundation_latest as (
    select
        account_id,
        arg_max(balance_near, date_day) filter (where read_with = 'transfers') as balance_transfers,
        arg_max(balance_near, date_day) filter (where read_with = 'view_account') as balance_view
    from {{ ref('stg_rpc__lockup_foundation_balances') }}
    where is_latest
    group by account_id
),

dune_assets as (select * from {{ ref('fct_dune_intents_asset_daily') }}),

last_intents_day as (select max(date_day) as d from intents where volume_usd_defillama is not null),

supply_both as (
    select * from {{ ref('fct_supply_daily') }}
    where total_supply_near is not null and onchain_supply_end_of_day_near is not null
),

market_30d as (
    select * from {{ ref('fct_market_daily') }}
    where date_day > (select max(date_day) from {{ ref('fct_market_daily') }} where price_usd_coinmetrics is not null) - 30
      and price_usd_coinmetrics is not null
),

chain_30d as (
    select * from {{ ref('fct_chain_daily') }}
    where date_day > (select max(date_day) from {{ ref('fct_chain_daily') }} where txns_v1 is not null and txns_v3 is not null) - 30
      and txns_v1 is not null and txns_v3 is not null
),

minted_30d as (
    select avg(minted_near) as minted_per_day, arg_max(total_supply_near, date_day) as supply
    from {{ ref('fct_supply_daily') }}
    where date_day > (select max(date_day) from {{ ref('fct_supply_daily') }}) - 30
),

config as (select arg_max(max_inflation_rate, snapshot_date) as max_inflation_rate from {{ ref('fct_protocol_config') }}),

latest_page_emissions as (
    select date_day, emissions_ytd_near, revenue_ytd_near from {{ ref('fct_revenue_page_emissions') }}
    order by date_day desc limit 1
),

minted_ytd as (
    select sum(s.minted_near) as minted
    from {{ ref('fct_supply_daily') }} s, latest_page_emissions p
    where s.date_day >= date_trunc('year', p.date_day) and s.date_day <= p.date_day
),

wallets_latest as (
    select account_id, arg_max(balance_near, date_day) as balance_near, arg_max(balance_near_nearblocks, date_day) as balance_near_nearblocks
    from {{ ref('fct_wallet_balance_daily') }}
    group by account_id
),

nearblocks_latest as (
    select account_id, arg_max(balance_near_nearblocks, date_day) as balance_near_nearblocks, max(date_day) as d
    from {{ ref('fct_wallet_balance_daily') }}
    where balance_near_nearblocks is not null
    group by account_id
),

wallet_at_nearblocks_day as (
    select n.account_id, n.d, b.balance_near, n.balance_near_nearblocks
    from nearblocks_latest n
    join {{ ref('fct_wallet_balance_daily') }} b on b.account_id = n.account_id and b.date_day = n.d
),

inflows as (
    select account_id, sum(received_near) as received_near, sum(received_usd) as received_usd
    from {{ ref('fct_revenue_inflows_daily') }}
    group by account_id
),

page_wallets as (
    select account_id, received_near from {{ ref('stg_revenue_page__wallets') }}
    where snapshot_date = (select max(snapshot_date) from {{ ref('stg_revenue_page__wallets') }})
),

etf_chain as (select * from {{ ref('fct_etf_nrr_chain_daily') }}),

etf_holdings as (
    select date_day, near_in_trust from {{ ref('fct_etf_nrr_daily') }} where near_in_trust is not null order by date_day desc limit 1
),

etf_reported as (
    select cumulative_flow_usd, reported_cumulative_usd from {{ ref('fct_etf_nrr_daily') }}
    where reported_cumulative_usd is not null order by date_day desc limit 1
),

checks as (
    select 'intents_volume_all_time_defillama_vs_page' as check_id, 'Intents all-time volume, USD' as metric, null as subject,
        'DefiLlama, sum of daily' as source_a, (select sum(volume_usd_defillama) from intents) as value_a,
        'revenue.near.org, cumulative' as source_b, (select max(cumulative_volume_usd_revenue_page) from intents) as value_b,
        3.0 as tolerance_pct, 'same_upstream' as independence

    union all select 'intents_volume_all_time_page_vs_dune', 'Intents all-time volume, USD', null,
        'revenue.near.org, cumulative on the reading''s last day', (select cumulative_volume_usd_revenue_page from intents, dune_day where date_day = d),
        'Dune public page, all scopes', (select value_usd from dune where metric = 'volume_all_time' and scope = 'all'),
        1.0, 'same_upstream'

    union all select 'intents_volume_all_time_nearblocks_vs_dune_public', 'Public Intents all-time volume, USD', null,
        'NearBlocks, cumulative on the reading''s last day', (select cumulative_volume_usd_nearblocks from intents, dune_day where date_day = d),
        'Dune public page, public scope', (select value_usd from dune where metric = 'volume_all_time' and scope = 'public'),
        3.0, 'independent'

    union all select 'intents_volume_30d_defillama_vs_page', 'Intents trailing 30-day volume, USD', null,
        'DefiLlama', (select sum(volume_usd_defillama) from intents, last_intents_day where date_day > d - 30),
        'revenue.near.org', (select sum(volume_usd_revenue_page) from intents, last_intents_day where date_day > d - 30),
        1.0, 'same_upstream'

    union all select 'intents_volume_2026_apr_aug_defillama_vs_nearblocks', 'Intents volume from 2026-04-01 to 2026-08-31, USD', null,
        'DefiLlama', (select sum(volume_usd_defillama) from intents where date_day between date '2026-04-01' and date '2026-08-31'),
        'NearBlocks, public Intents only', (select sum(volume_usd_nearblocks) from intents where date_day between date '2026-04-01' and date '2026-08-31'),
        1.0, 'independent'

    union all select 'intents_volume_2026_apr_aug_defillama_vs_page', 'Intents volume from 2026-04-01 to 2026-08-31, USD', null,
        'DefiLlama', (select sum(volume_usd_defillama) from intents where date_day between date '2026-04-01' and date '2026-08-31'),
        'revenue.near.org, all routes', (select sum(volume_usd_revenue_page) from intents where date_day between date '2026-04-01' and date '2026-08-31'),
        3.0, 'same_upstream'

    union all select 'intents_fees_all_time_defillama_vs_page', 'Intents all-time gross fees, USD', null,
        'DefiLlama, sum of daily', (select sum(fees_usd_defillama) from intents),
        'revenue.near.org, cumulative', (select max(fees_usd) from (select sum(fees_usd_revenue_page) as fees_usd from intents)),
        3.0, 'same_upstream'

    union all select 'intents_fees_all_time_page_vs_dune', 'Intents all-time gross fees, USD', null,
        'revenue.near.org, through the reading''s last day', (select sum(fees_usd_revenue_page) from intents, dune_day where date_day <= d),
        'Dune public page', (select value_usd from dune where metric = 'total_generated_fees' and scope = 'all'),
        1.0, 'same_upstream'

    union all select 'intents_fee_channels_vs_total', 'Listed fee channels vs total fees, USD', null,
        'Dune public page, sum of 100 listed channels', (select sum(fees_usd) from {{ ref('fct_intents_fee_channels') }}
            where snapshot_date = (select max(snapshot_date) from {{ ref('fct_intents_fee_channels') }})),
        'Dune public page, total', (select value_usd from dune where metric = 'total_generated_fees' and scope = 'all'),
        5.0, 'same_upstream'

    union all select 'intents_volume_dune_assets_vs_defillama', 'Intents volume over the days read per asset, USD', null,
        'Dune public page, sum of assets', (select sum(volume_usd) from dune_assets),
        'DefiLlama, same days', (select sum(volume_usd_defillama) from intents where date_day in (select date_day from dune_assets)),
        1.0, 'same_upstream'

    union all select 'intents_volume_30d_dune_assets_vs_tile', 'Intents trailing 30-day volume, USD', null,
        'Dune public page, sum of assets', (select sum(volume_usd) from dune_assets where date_day > (select max(date_day) from dune_assets) - 30),
        'Dune public page, all scopes', (select value_usd from dune where metric = 'volume_30d' and scope = 'all'),
        1.0, 'same_upstream'

    union all select 'intents_revenue_all_time_defillama_vs_wallets', 'Intents captured revenue, USD', null,
        'DefiLlama, sum of daily', (select sum(revenue_usd_defillama) from intents),
        'Wallet transfers, same method', (select sum(received_usd) from inflows),
        15.0, 'independent'

    union all select 'intents_revenue_all_time_defillama_vs_page_monthly', 'Intents captured revenue, USD', null,
        'DefiLlama, sum of daily', (select sum(revenue_usd_defillama) from intents),
        'revenue.near.org, monthly cumulative', (select max(cumulative_revenue_usd) from {{ ref('fct_revenue_page_monthly') }}),
        5.0, 'same_upstream'

    union all select 'intents_revenue_near_page_wallets_vs_transfers', 'NEAR received per revenue wallet', w.account_id,
        'revenue.near.org wallet table', w.received_near,
        'Wallet transfers', i.received_near,
        10.0, 'independent'
    from page_wallets w left join inflows i using (account_id)

    union all select 'intents_confidential_tvl_page_vs_dune', 'Confidential Intents TVL, USD', null,
        'revenue.near.org, on the reading''s last day', (select arg_max(confidential_tvl_usd, date_day) from intents, dune_day where confidential_tvl_usd is not null and date_day <= d),
        'Dune public page', (select value_usd from dune where metric = 'tvl' and scope = 'confidential'),
        5.0, 'same_upstream'

    union all select 'intents_public_tvl_dune_vs_defillama', 'Public Intents TVL, USD', null,
        'Dune public page', (select value_usd from dune where metric = 'tvl' and scope = 'public'),
        'DefiLlama protocol TVL, on the reading''s last day', (select arg_max(tvl_usd, date_day) from {{ ref('fct_protocol_tvl_daily') }}, dune_day where protocol_slug = 'near-intents' and date_day <= d),
        15.0, 'independent'

    union all select 'supply_latest_nearblocks_vs_chain', 'Total supply at day end, NEAR', null,
        'NearBlocks /v1/charts', (select arg_max(total_supply_near, date_day) from supply_both),
        'Archival RPC, first block of next day', (select arg_max(onchain_supply_end_of_day_near, date_day) from supply_both),
        0.05, 'independent'

    union all select 'circulating_supply_latest_nearblocks_vs_coinmetrics', 'What other services report as circulating supply on the latest day, NEAR', null,
        'NearBlocks /v1/charts', (select circulating_supply_near_nearblocks from market_latest_cm),
        'CoinMetrics market cap divided by price', (select market_cap_usd_coinmetrics / price_usd_coinmetrics from market_latest_cm),
        2.0, 'same_upstream'

    union all select 'circulating_supply_latest_chain_vs_coinmetrics', 'Circulating supply on the latest day, NEAR', null,
        'Total supply minus lockups, read on chain', (select circulating_supply_near from market_latest_cm),
        'CoinMetrics market cap divided by price', (select market_cap_usd_coinmetrics / price_usd_coinmetrics from market_latest_cm),
        1.0, 'independent'

    union all select 'circulating_supply_last_live_day_chain_vs_nearblocks', 'Circulating supply on 2025-08-26, the last day NearBlocks computed it, NEAR', null,
        'Total supply minus lockups, read on chain', (select circulating_supply_near from {{ ref('fct_supply_daily') }}, nearblocks_last_live where date_day = d),
        'NearBlocks /v1/charts', (select circulating_supply_near_nearblocks from {{ ref('fct_supply_daily') }}, nearblocks_last_live where date_day = d),
        0.1, 'independent'

    union all select 'circulating_supply_year_mean_chain_vs_nearblocks', 'Mean circulating supply through 2025-08-26, NEAR', cast(y as varchar),
        'Total supply minus lockups, read on chain', chain,
        'NearBlocks /v1/charts', nearblocks,
        1.0, 'independent'
    from circulating_years

    union all select 'circulating_supply_chain_vs_published_schedule', 'Circulating supply, NEAR', p.label,
        'Total supply minus lockups, read on chain', s.circulating_supply_near,
        'NEAR''s published schedule, last updated 2020-10-16', p.value,
        5.0, 'independent'
    from published_supply p left join {{ ref('fct_supply_daily') }} s on s.date_day = p.reading_date

    union all select 'lockup_locked_latest_formula_vs_contract_views', 'NEAR locked in lockups still running at the latest read', null,
        'Schedule formula', (select sum({{ lockup_locked_near('v.block_ns') }}) from latest_lockup_views v join lockup_schedules using (lockup_no)),
        'Contracts'' get_locked_amount', (select sum(contract_locked_near) from latest_lockup_views),
        0.1, 'same_upstream'

    union all select 'foundation_balance_transfers_vs_chain', 'Balance of an account NEAR Explorer subtracted, NEAR', account_id,
        'FastNear running balance', balance_transfers,
        'RPC view_account', balance_view,
        1.0, 'independent'
    from foundation_latest

    union all select 'market_cap_2026_06_15_chain_vs_bitwise_prospectus', 'NEAR market cap on 2026-06-15, USD', null,
        'Price times chain-built circulating supply', (select market_cap_usd from {{ ref('fct_market_daily') }} where date_day = date '2026-06-15'),
        'Bitwise NEAR ETF prospectus, rounded', (select value from {{ ref('near_supply_readings') }} where reading = 'market_cap' and reading_date = date '2026-06-15'),
        3.0, 'independent'

    union all select 'issuance_rate_30d_minted_vs_config', 'Annual issuance rate, trailing 30 days', null,
        'Supply change plus burn', (select minted_per_day * 365 / supply from minted_30d),
        'Protocol config max_inflation_rate', (select max_inflation_rate from config),
        5.0, 'independent'

    union all select 'treasury_share_30d_config_vs_epoch_rewards', 'Share of issuance sent to treasury.near', null,
        'Protocol config protocol_reward_rate', (select arg_max(protocol_reward_rate, snapshot_date) from {{ ref('fct_protocol_config') }}),
        'EpochRewards to treasury.near over 30 days, divided by minted',
        (select sum(treasury_reward_near) / nullif(sum(minted_near), 0) from {{ ref('fct_supply_daily') }}
            where date_day > (select max(date_day) from {{ ref('fct_supply_daily') }}) - 30),
        5.0, 'independent'

    union all select 'emissions_ytd_page_vs_supply', 'Emissions this year, NEAR', null,
        'revenue.near.org', (select emissions_ytd_near from latest_page_emissions),
        'Supply change plus burn', (select minted from minted_ytd),
        3.0, 'independent'

    union all select 'price_30d_coinbase_vs_coinmetrics', 'Mean NEAR close over 30 days, USD', null,
        'Coinbase', (select avg(price_usd_coinbase_close) from market_30d where price_usd_coinbase_close is not null),
        'CoinMetrics', (select avg(price_usd_coinmetrics) from market_30d where price_usd_coinbase_close is not null),
        2.0, 'independent'

    union all select 'price_30d_defillama_vs_coinmetrics', 'Mean NEAR close over 30 days, USD', null,
        'DefiLlama', (select avg(price_usd_defillama) from market_30d where price_usd_defillama is not null),
        'CoinMetrics', (select avg(price_usd_coinmetrics) from market_30d where price_usd_defillama is not null),
        2.0, 'independent'

    union all select 'price_30d_nearblocks_vs_coinmetrics', 'Mean NEAR close over 30 days, USD', null,
        'NearBlocks', (select avg(price_usd_nearblocks) from market_30d where price_usd_nearblocks is not null),
        'CoinMetrics', (select avg(price_usd_coinmetrics) from market_30d where price_usd_nearblocks is not null),
        2.0, 'independent'

    union all select 'txns_30d_v1_vs_v3', 'Mean daily transactions over 30 days', null,
        'NearBlocks v1', (select avg(txns_v1) from chain_30d),
        'NearBlocks v3', (select avg(txns_v3) from chain_30d),
        1.0, 'same_upstream'

    union all select 'active_accounts_30d_v1_vs_v3', 'Mean daily active accounts over 30 days', null,
        'NearBlocks v1', (select avg(active_accounts_v1) from chain_30d),
        'NearBlocks v3', (select avg(active_accounts_v3) from chain_30d),
        5.0, 'same_upstream'

    union all select 'tvl_latest_defillama_vs_nearblocks', 'NEAR chain TVL, USD', null,
        'DefiLlama', (select tvl_usd from {{ ref('fct_peer_daily') }} where chain_id = 'near' and tvl_usd is not null order by date_day desc limit 1),
        'NearBlocks', (select tvl_usd from {{ ref('stg_nearblocks__tvl_stats') }} where is_latest order by date_day desc limit 1),
        10.0, 'independent'

    union all select 'stablecoins_latest_chain_vs_assets', 'Stablecoins on NEAR, USD', null,
        'DefiLlama chain series', (select stablecoins_usd from {{ ref('fct_peer_daily') }} where chain_id = 'near' and stablecoins_usd is not null order by date_day desc limit 1),
        'DefiLlama, sum of assets', (select sum(circulating) from {{ ref('fct_stablecoin_assets') }}
            where chain_id = 'near' and snapshot_date = (select max(snapshot_date) from {{ ref('fct_stablecoin_assets') }})),
        5.0, 'same_upstream'

    union all select 'wallet_balance_transfers_vs_chain', 'Native balance, NEAR', w.account_id,
        'FastNear running balance', w.balance_near,
        'RPC view_account', e.balance_near,
        1.0, 'independent'
    from wallets_latest w left join {{ ref('dim_entity') }} e using (account_id)

    union all select 'wallet_balance_transfers_vs_nearblocks', 'Native balance, NEAR', account_id,
        'FastNear running balance', balance_near,
        'NearBlocks daily balance', balance_near_nearblocks,
        1.0, 'independent'
    from wallet_at_nearblocks_day

    union all select 'etf_nrr_shares_chain_vs_fund', 'Bitwise NEAR ETF shares outstanding', null,
        'Chain, whole baskets settled', (select arg_max(running_settled_shares, date_day) from etf_chain),
        'Bitwise page and reports, last known', (select arg_max(shares_outstanding, date_day) from {{ ref('fct_etf_nrr_daily') }} where shares_outstanding is not null),
        5.0, 'independent'

    union all select 'etf_nrr_near_chain_vs_fund', 'NEAR held by the Bitwise NEAR ETF', null,
        'Chain, listed wallets in the staking pool', (select arg_max(c.near_in_wallets, c.date_day) from etf_chain c, etf_holdings h where c.date_day <= h.date_day),
        'Bitwise page, NEAR in trust', (select near_in_trust from etf_holdings),
        1.0, 'independent'

    union all select 'etf_nrr_cumulative_flow_vs_reported', 'Bitwise NEAR ETF cumulative net inflow, USD', null,
        'Share changes times NAV', (select cumulative_flow_usd from etf_reported),
        'SoSoValue, through news reports', (select reported_cumulative_usd from etf_reported),
        1.0, 'same_upstream'
)

select
    c.check_id,
    c.metric,
    c.subject,
    c.source_a,
    cast(c.value_a as double) as value_a,
    c.source_b,
    cast(c.value_b as double) as value_b,
    100.0 * abs(cast(c.value_a as double) - cast(c.value_b as double))
        / nullif(greatest(abs(cast(c.value_a as double)), abs(cast(c.value_b as double))), 0) as diff_pct,
    c.tolerance_pct,
    c.independence,
    case
        when c.value_a is null or c.value_b is null then 'not_available'
        when 100.0 * abs(cast(c.value_a as double) - cast(c.value_b as double))
            / nullif(greatest(abs(cast(c.value_a as double)), abs(cast(c.value_b as double))), 0) <= c.tolerance_pct then 'agree'
        else 'differs'
    end as status,
    n.explanation
from checks c
left join {{ ref('reconciliation_notes') }} n using (check_id)
