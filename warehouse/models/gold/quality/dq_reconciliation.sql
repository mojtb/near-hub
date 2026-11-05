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
    where price_usd_coinmetrics is not null and market_cap_usd is not null and circulating_supply_near is not null
    order by date_day desc limit 1
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

prices_latest as (
    select * from {{ ref('fct_token_prices') }}
    where snapshot_date = (select max(snapshot_date) from {{ ref('fct_token_prices') }})
),

lst_latest as (
    select token, contract, cast(price_near as double) as price_near
    from {{ ref('fct_lst_snapshot') }}
    where snapshot_date = (select max(snapshot_date) from prices_latest)
),

holdings_latest as (
    select * from {{ ref('fct_wallet_holdings') }}
    where snapshot_date = (select max(snapshot_date) from {{ ref('fct_wallet_holdings') }})
),

protocol_tvl_latest as (
    select protocol_slug, arg_max(tvl_usd, date_day) as tvl_usd
    from {{ ref('fct_protocol_tvl_daily') }}
    group by protocol_slug
),

-- Bridged assets are most of what intents.near holds, so until the metadata backlog gives them decimals its sum means little.
intents_holdings as (
    select case
        when count(*) filter (where value_status = 'no_decimals' and price_source = 'oneclick') <= 0.05 * count(*) filter (where price_source = 'oneclick')
        then sum(value_usd)
    end as value_usd
    from holdings_latest
    where account_id = 'intents.near'
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

    union all select 'circulating_supply_latest_nearblocks_vs_coinmetrics', 'Circulating supply on the latest day, NEAR', null,
        'NearBlocks /v1/charts', (select circulating_supply_near from market_latest_cm),
        'CoinMetrics market cap divided by price', (select market_cap_usd / price_usd_coinmetrics from market_latest_cm),
        2.0, 'independent'

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

    union all select 'token_prices_latest_rhea_vs_oneclick', 'Median token price as a multiple of 1Click''s, over tokens both lists price', null,
        'Rhea', (select median(price_usd_rhea / price_usd_oneclick) from prices_latest where token_id <> 'native:near'),
        'Parity with 1Click', 1.0,
        2.0, 'independent'

    union all select 'lst_price_latest_lists_vs_contract', 'Liquid staking token price, USD', l.token,
        'fct_token_prices', p.price_usd,
        'Contract rate times wrap.near''s price', l.price_near * w.price_usd,
        3.0, 'independent'
    from lst_latest l
    left join prices_latest p on p.token_id = l.contract
    left join prices_latest w on w.token_id = 'wrap.near'

    union all select 'holdings_usd_latest_vs_tvl', 'USD held by a protocol''s contracts against its TVL', 'Rhea lending',
        'contract.main.burrow.near, sum of value_usd', (select sum(value_usd) from holdings_latest where account_id = 'contract.main.burrow.near'),
        'DefiLlama rhea-lend', (select tvl_usd from protocol_tvl_latest where protocol_slug = 'rhea-lend'),
        20.0, 'independent'

    union all select 'holdings_usd_latest_vs_tvl', 'USD held by a protocol''s contracts against its TVL', 'Rhea DEX',
        'v2.ref-finance.near and dclv2.ref-labs.near, sum of value_usd', (select sum(value_usd) from holdings_latest where account_id in ('v2.ref-finance.near', 'dclv2.ref-labs.near')),
        'DefiLlama rhea-dex', (select tvl_usd from protocol_tvl_latest where protocol_slug = 'rhea-dex'),
        30.0, 'independent'

    union all select 'holdings_usd_latest_vs_tvl', 'USD held by a protocol''s contracts against its TVL', 'NEAR Intents',
        'intents.near, sum of value_usd', (select value_usd from intents_holdings),
        'DefiLlama near-intents plus revenue.near.org confidential TVL',
        (select tvl_usd from protocol_tvl_latest where protocol_slug = 'near-intents')
            + (select arg_max(confidential_tvl_usd, date_day) from intents where confidential_tvl_usd is not null),
        20.0, 'independent'
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
