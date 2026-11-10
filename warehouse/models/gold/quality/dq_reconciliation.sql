-- depends_on: {{ ref('stg_nearblocks__charts_v1') }}, {{ ref('stg_nearblocks__price_stats') }}
-- Every place two sources should tell the same story, side by side. Gold keeps one column per measure, so the sources a
-- gold table chooses between are read here from silver. `independence` matters: DefiLlama and revenue.near.org both read
-- NEAR's own Dune uploads, so their agreement proves little. NearBlocks, the wallet transfers and the chain itself are
-- independent checks. A gap beyond tolerance must have a written explanation in registry/reconciliation_notes.csv, or
-- `make verify` fails.
with intents as (select * from {{ ref('fct_intents_daily') }}),

-- The Intents sources fct_intents_daily chooses between.
llama_volume as (select date_day, volume_usd from {{ ref('stg_defillama__intents_volume') }} where is_latest),

llama_fees as (
    select date_day, sum(value_usd) as fees_usd
    from {{ ref('stg_defillama__intents_fees') }}
    where is_latest and data_type = 'dailyFees'
    group by date_day
),

page_volume as (select date_day, volume_usd, cumulative_volume_usd from {{ ref('stg_revenue_page__volume_daily') }} where is_latest),
page_fees as (select date_day, fees_usd from {{ ref('stg_revenue_page__fees_daily') }} where is_latest),

dune as (
    select metric, scope, value_usd from {{ ref('fct_intents_dashboard_readings') }}
    where snapshot_date = (select max(snapshot_date) from {{ ref('fct_intents_dashboard_readings') }})
),

-- A dashboard reading is taken by hand, so it stands still while the daily series move on. Its all-time tiles are
-- therefore compared with the other source on the reading's last full day, which is what the tiles covered.
dune_day as (
    select max(snapshot_date) - 1 as d from {{ ref('fct_intents_dashboard_readings') }}
),

dune_assets as (select * from {{ ref('fct_dune_intents_asset_daily') }}),

last_llama_day as (select max(date_day) as d from llama_volume),

-- NEAR's price per source, each as the close of the UTC day.
coinmetrics as (
    select date_day, price_usd, market_cap_usd from {{ ref('stg_coinmetrics__asset_metrics') }}
    where is_latest and coinmetrics_asset = 'near'
),

coinbase_close as (select date_day, close_usd from {{ ref('stg_coinbase__candles') }} where is_latest),
defillama_price as (select date_day, price_usd from {{ ref('stg_defillama__peer_price') }} where is_latest and coin_id = 'near'),
nearblocks_price as ({{ nearblocks_daily_close() }}),

prices as (
    select
        k.date_day,
        cm.price_usd as price_usd_coinmetrics,
        cb.close_usd as price_usd_coinbase_close,
        dl.price_usd as price_usd_defillama,
        nb.price_usd as price_usd_nearblocks
    from (
        select date_day from coinmetrics union select date_day from coinbase_close
        union select date_day from defillama_price union select date_day from nearblocks_price
    ) k
    left join coinmetrics cm using (date_day)
    left join coinbase_close cb using (date_day)
    left join defillama_price dl using (date_day)
    left join nearblocks_price nb using (date_day)
),

market_30d as (
    select * from prices
    where date_day > (select max(date_day) from prices where price_usd_coinmetrics is not null) - 30
      and price_usd_coinmetrics is not null
),

nearblocks_v1 as (select * from {{ ref('stg_nearblocks__charts_v1') }} where is_latest),

market_latest_cm as (
    select
        cm.date_day,
        cm.price_usd as price_usd_coinmetrics,
        cm.market_cap_usd as market_cap_usd_coinmetrics,
        nb.circulating_supply_near as circulating_supply_near_nearblocks,
        cs.circulating_supply_near
    from coinmetrics cm
    join nearblocks_v1 nb using (date_day)
    left join {{ ref('fct_circulating_supply_daily') }} cs using (date_day)
    where cm.price_usd is not null and cm.market_cap_usd is not null and nb.circulating_supply_near is not null
    order by cm.date_day desc limit 1
),

-- CoinMetrics' market cap for NEAR has been its price times the previous day's total supply since 2025-10-25 (see the note
-- on circulating_supply_latest_nearblocks_vs_coinmetrics), so it is a fully diluted value. An earlier check set it against
-- the chain-built circulating supply and agreed only because 99.84% of supply is unlocked; this one says what it is.
coinmetrics_supply as (
    select cm.market_cap_usd / cm.price_usd as implied_supply_near, s.total_supply_near
    from coinmetrics cm
    join {{ ref('fct_supply_daily') }} s on s.date_day = cm.date_day - 1
    where cm.price_usd is not null and cm.market_cap_usd is not null
    order by cm.date_day desc limit 1
),

-- Before issuance began nothing was minted, so every fall in supply was gas burned: the only days on which the burn
-- can be read off the chain and set against the 70% of gas that burn_near assumes.
burn_before_issuance as (
    select sum(burn_near) as burn_model_near, sum(-supply_change_near) as supply_fall_near
    from {{ ref('fct_supply_daily') }}
    where supply_change_near < 0
      and date_day < (select min(date_day) from {{ ref('fct_supply_daily') }} where supply_change_near > 0)
),

-- NearBlocks stopped computing circulating supply on this day, so it is the last day its figure can test the chain-built one.
nearblocks_last_live as (select date '2025-08-26' as d),

circulating_years as (
    select
        year(cs.date_day) as y,
        avg(cs.circulating_supply_near) as chain,
        avg(nb.circulating_supply_near) as nearblocks
    from {{ ref('fct_circulating_supply_daily') }} cs
    join nearblocks_v1 nb using (date_day)
    cross join nearblocks_last_live
    where cs.date_day <= d and nb.circulating_supply_near is not null
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

-- Total supply against the chain's own figure in the first block of the next day.
supply_both as (
    select s.date_day, s.total_supply_near, b.total_supply_near as onchain_supply_end_of_day_near
    from {{ ref('fct_supply_daily') }} s
    join {{ ref('dim_block_day') }} b on b.date_day = s.date_day + 1
    where s.total_supply_near is not null
),

-- The NearBlocks counts that /v1 and /v3 both serve, over the latest 30 days both hold.
v1_v3 as (
    select
        v1.date_day,
        v1.txns as txns_v1, t.txns as txns_v3,
        v1.active_accounts as active_accounts_v1, a.active_accounts as active_accounts_v3,
        v1.active_contracts as active_contracts_v1, a.active_contracts as active_contracts_v3,
        v1.txn_fee_near as txn_fee_near_v1, t.txn_fee_near as txn_fee_near_v3,
        v1.gas_fee_near as gas_fee_near_v1, b.gas_fee_near as gas_fee_near_v3
    from nearblocks_v1 v1
    join (select * from {{ ref('stg_nearblocks__txn_stats') }} where is_latest) t using (date_day)
    left join (select * from {{ ref('stg_nearblocks__address_stats') }} where is_latest) a using (date_day)
    left join (select * from {{ ref('stg_nearblocks__block_stats') }} where is_latest) b using (date_day)
),

chain_30d as (select * from v1_v3 where date_day > (select max(date_day) from v1_v3) - 30),

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
    select account_id, arg_max(balance_near, date_day) as balance_near
    from {{ ref('fct_wallet_balance_daily') }}
    group by account_id
),

nearblocks_balances as (
    select account_id, date_day, balance_near from {{ ref('stg_nearblocks__wallet_balance') }} where is_latest
),

-- The newest day each crawled wallet has a NearBlocks balance for.
wallet_at_nearblocks_day as (
    select b.account_id, b.date_day as d, b.balance_near, n.balance_near as balance_near_nearblocks
    from {{ ref('fct_wallet_balance_daily') }} b
    join nearblocks_balances n using (account_id, date_day)
    qualify row_number() over (partition by b.account_id order by b.date_day desc) = 1
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
    select h.*, p.price_source
    from {{ ref('fct_wallet_holdings') }} h
    left join {{ ref('fct_token_prices') }} p on p.snapshot_date = h.snapshot_date and p.token_id = h.token_id
    where h.snapshot_date = (select max(snapshot_date) from {{ ref('fct_wallet_holdings') }})
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

-- Transactions to the Chain Signatures contract, from NearBlocks' signer statistics and from its per-contract statistics.
signer_30d as (
    select s.date_day, s.txns as signer_stats_txns, c.txns as contract_stats_txns
    from {{ ref('fct_chain_signatures_daily') }} s
    join {{ ref('fct_contract_daily') }} c on c.date_day = s.date_day and c.account_id = 'v1.signer'
    where s.date_day > (select max(date_day) from {{ ref('fct_chain_signatures_daily') }}) - 30
),

mpc_threshold as (
    select s.snapshot_date, s.threshold as contract_threshold, max(o.threshold) as nearblocks_threshold
    from {{ ref('fct_mpc_state') }} s
    join {{ ref('stg_nearblocks__mpc_operators') }} o using (snapshot_date)
    group by s.snapshot_date, s.threshold
    order by s.snapshot_date desc limit 1
),

-- GitHub's weekly statistic against the default-branch count gold uses, for the repository the catalog cites.
nearcore_commits as (
    select sum(s.commits) as statistic, sum(l.commits) as default_branch
    from {{ ref('stg_github__weekly_commits') }} s
    join {{ ref('stg_github__weekly_commits_list') }} l using (repo, week_start)
    where s.is_latest and l.is_latest and s.repo = 'near/nearcore'
),

-- NEAR's transaction fees in USD from two indexers, over the latest 30 days both hold. DefiLlama's chain adapter sums
-- them from Allium's index and prices them itself; the other side is NearBlocks' fee in NEAR at this warehouse's close.
near_gas as (
    select g.date_day, g.gas_fees_usd as defillama_usd, c.txn_fee_near * m.price_usd as nearblocks_usd
    from {{ ref('stg_defillama__chain_gas_fees') }} g
    join {{ ref('fct_chain_daily') }} c using (date_day)
    join {{ ref('fct_market_daily') }} m using (date_day)
    where g.is_latest and g.llama_chain = 'Near'
),

near_gas_30d as (select * from near_gas where date_day > (select max(date_day) from near_gas) - 30),

checks as (
    select 'intents_volume_all_time_defillama_vs_page' as check_id, 'Intents all-time volume, USD' as metric, null as subject,
        'DefiLlama, sum of daily' as source_a, (select sum(volume_usd) from llama_volume) as value_a,
        'revenue.near.org, cumulative' as source_b, (select max(cumulative_volume_usd) from page_volume) as value_b,
        3.0 as tolerance_pct, 'same_upstream' as independence

    union all select 'intents_volume_all_time_page_vs_dune', 'Intents all-time volume, USD', null,
        'revenue.near.org, cumulative on the reading''s last day', (select cumulative_volume_usd from page_volume, dune_day where date_day = d),
        'Dune public page, all scopes', (select value_usd from dune where metric = 'volume_all_time' and scope = 'all'),
        1.0, 'same_upstream'

    union all select 'intents_volume_all_time_nearblocks_vs_dune_public', 'Public Intents all-time volume, USD', null,
        'NearBlocks, cumulative on the reading''s last day', (select public_volume_cumulative_usd from intents, dune_day where date_day = d),
        'Dune public page, public scope', (select value_usd from dune where metric = 'volume_all_time' and scope = 'public'),
        3.0, 'independent'

    union all select 'intents_volume_30d_defillama_vs_page', 'Intents trailing 30-day volume, USD', null,
        'DefiLlama', (select sum(volume_usd) from llama_volume, last_llama_day where date_day > d - 30),
        'revenue.near.org', (select sum(volume_usd) from page_volume, last_llama_day where date_day > d - 30 and date_day <= d),
        1.0, 'same_upstream'

    union all select 'intents_volume_2026_apr_aug_defillama_vs_nearblocks', 'Intents volume from 2026-04-01 to 2026-08-31, USD', null,
        'DefiLlama', (select sum(volume_usd) from llama_volume where date_day between date '2026-04-01' and date '2026-08-31'),
        'NearBlocks, public Intents only', (select sum(public_volume_usd) from intents where date_day between date '2026-04-01' and date '2026-08-31'),
        1.0, 'independent'

    union all select 'intents_volume_2026_apr_aug_defillama_vs_page', 'Intents volume from 2026-04-01 to 2026-08-31, USD', null,
        'DefiLlama', (select sum(volume_usd) from llama_volume where date_day between date '2026-04-01' and date '2026-08-31'),
        'revenue.near.org, all routes', (select sum(volume_usd) from page_volume where date_day between date '2026-04-01' and date '2026-08-31'),
        3.0, 'same_upstream'

    union all select 'intents_volume_30d_nearblocks_vs_dune_public', 'Public Intents volume over the 30 days the latest Dune reading covers, USD', null,
        'NearBlocks, public Intents', (select sum(public_volume_usd) from intents, dune_day where date_day > d - 30 and date_day <= d),
        'Dune public page, public scope', (select value_usd from dune where metric = 'volume_30d' and scope = 'public'),
        5.0, 'independent'

    union all select 'intents_fees_all_time_defillama_vs_page', 'Intents all-time gross fees, USD', null,
        'DefiLlama, sum of daily', (select sum(fees_usd) from llama_fees),
        'revenue.near.org, sum of daily', (select sum(fees_usd) from page_fees),
        3.0, 'same_upstream'

    union all select 'intents_fees_all_time_page_vs_dune', 'Intents all-time gross fees, USD', null,
        'revenue.near.org, through the reading''s last day', (select sum(fees_usd) from page_fees, dune_day where date_day <= d),
        'Dune public page', (select value_usd from dune where metric = 'total_generated_fees' and scope = 'all'),
        1.0, 'same_upstream'

    union all select 'intents_fee_channels_vs_total', 'Listed fee channels vs total fees, USD', null,
        'Dune public page, sum of 100 listed channels', (select sum(fees_usd) from {{ ref('fct_intents_fee_channels') }}
            where snapshot_date = (select max(snapshot_date) from {{ ref('fct_intents_fee_channels') }})),
        'Dune public page, total', (select value_usd from dune where metric = 'total_generated_fees' and scope = 'all'),
        5.0, 'same_upstream'

    union all select 'intents_volume_dune_assets_vs_defillama', 'Intents volume over the days read per asset, USD', null,
        'Dune public page, sum of assets', (select sum(volume_usd) from dune_assets),
        'DefiLlama, same days', (select sum(volume_usd) from llama_volume where date_day in (select date_day from dune_assets)),
        1.0, 'same_upstream'

    union all select 'intents_volume_30d_dune_assets_vs_tile', 'Intents trailing 30-day volume, USD', null,
        'Dune public page, sum of assets', (select sum(volume_usd) from dune_assets where date_day > (select max(date_day) from dune_assets) - 30),
        'Dune public page, all scopes', (select value_usd from dune where metric = 'volume_30d' and scope = 'all'),
        1.0, 'same_upstream'

    union all select 'intents_revenue_all_time_defillama_vs_wallets', 'Intents captured revenue, USD', null,
        'DefiLlama, sum of daily', (select sum(revenue_usd) from intents),
        'Wallet transfers, same method', (select sum(received_usd) from inflows),
        3.0, 'independent'

    union all select 'intents_revenue_all_time_defillama_vs_page_monthly', 'Intents captured revenue, USD', null,
        'DefiLlama, sum of daily', (select sum(revenue_usd) from intents),
        'revenue.near.org, monthly series summed', (select sum(revenue_usd) from {{ ref('fct_revenue_page_monthly') }}),
        5.0, 'same_upstream'

    union all select 'intents_revenue_near_page_wallets_vs_transfers', 'NEAR received per revenue wallet', w.account_id,
        'revenue.near.org wallet table', w.received_near,
        'Wallet transfers', i.received_near,
        3.0, 'independent'
    from page_wallets w left join inflows i using (account_id)

    union all select 'intents_confidential_tvl_page_vs_dune', 'Confidential Intents TVL, USD', null,
        'revenue.near.org, on the reading''s last day', (select arg_max(confidential_tvl_usd, date_day) from intents, dune_day where confidential_tvl_usd is not null and date_day <= d),
        'Dune public page', (select value_usd from dune where metric = 'tvl' and scope = 'confidential'),
        1.0, 'same_upstream'

    union all select 'intents_public_tvl_dune_vs_defillama', 'Public Intents TVL, USD', null,
        'Dune public page', (select value_usd from dune where metric = 'tvl' and scope = 'public'),
        'DefiLlama protocol TVL, on the reading''s last day', (select arg_max(tvl_usd, date_day) from {{ ref('fct_protocol_tvl_daily') }}, dune_day where protocol_slug = 'near-intents' and date_day <= d),
        15.0, 'independent'

    union all select 'supply_latest_nearblocks_vs_chain', 'Total supply at day end, NEAR', null,
        'NearBlocks', (select arg_max(total_supply_near, date_day) from supply_both),
        'Archival RPC, first block of next day', (select arg_max(onchain_supply_end_of_day_near, date_day) from supply_both),
        0.05, 'independent'

    union all select 'circulating_supply_latest_nearblocks_vs_coinmetrics', 'What other services report as circulating supply on the latest day, NEAR', null,
        'NearBlocks /v1/charts', (select circulating_supply_near_nearblocks from market_latest_cm),
        'CoinMetrics market cap divided by price', (select market_cap_usd_coinmetrics / price_usd_coinmetrics from market_latest_cm),
        2.0, 'same_upstream'

    union all select 'coinmetrics_supply_latest_vs_total_supply', 'Supply behind CoinMetrics'' market cap on its latest day, NEAR', null,
        'CoinMetrics market cap divided by price', (select implied_supply_near from coinmetrics_supply),
        'Total supply at the end of the day before', (select total_supply_near from coinmetrics_supply),
        0.05, 'same_upstream'

    union all select 'burn_before_issuance_model_vs_supply_fall', 'NEAR burned on the days before issuance began', null,
        'fct_supply_daily.burn_near: 70% of gas fees', (select burn_model_near from burn_before_issuance),
        'Fall in total supply on the same days', (select supply_fall_near from burn_before_issuance),
        5.0, 'same_upstream'

    union all select 'circulating_supply_last_live_day_chain_vs_nearblocks', 'Circulating supply on 2025-08-26, the last day NearBlocks computed it, NEAR', null,
        'Total supply minus lockups, read on chain', (select circulating_supply_near from {{ ref('fct_circulating_supply_daily') }}, nearblocks_last_live where date_day = d),
        'NearBlocks /v1/charts', (select circulating_supply_near from nearblocks_v1, nearblocks_last_live where date_day = d),
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
    from published_supply p left join {{ ref('fct_circulating_supply_daily') }} s on s.date_day = p.reading_date

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

    union all select 'txn_fee_30d_v1_vs_v3', 'Mean daily transaction fees over 30 days, NEAR', null,
        'NearBlocks v1', (select avg(txn_fee_near_v1) from chain_30d),
        'NearBlocks v3', (select avg(txn_fee_near_v3) from chain_30d),
        1.0, 'same_upstream'

    union all select 'gas_fee_30d_v1_vs_v3', 'Mean daily gas fees over 30 days, NEAR', null,
        'NearBlocks /v1/charts', (select avg(gas_fee_near_v1) from chain_30d),
        'NearBlocks /v3/block-stats', (select avg(gas_fee_near_v3) from chain_30d),
        0.1, 'same_upstream'

    union all select 'near_gas_fees_30d_defillama_vs_nearblocks', 'NEAR transaction fees over 30 days, USD', null,
        'DefiLlama chain adapter, from Allium', (select sum(defillama_usd) from near_gas_30d),
        'NearBlocks fee in NEAR at the day''s close', (select sum(nearblocks_usd) from near_gas_30d),
        3.0, 'independent'

    union all select 'active_contracts_30d_v1_vs_v3', 'Mean daily active contracts over 30 days', null,
        'NearBlocks v1', (select avg(active_contracts_v1) from chain_30d),
        'NearBlocks v3', (select avg(active_contracts_v3) from chain_30d),
        1.0, 'same_upstream'

    union all select 'active_accounts_30d_v1_vs_v3', 'Mean daily active accounts over 30 days', null,
        'NearBlocks v1', (select avg(active_accounts_v1) from chain_30d),
        'NearBlocks v3', (select avg(active_accounts_v3) from chain_30d),
        5.0, 'same_upstream'

    union all select 'signer_txns_30d_signer_stats_vs_contract_stats', 'Mean daily transactions to v1.signer over 30 days', null,
        'NearBlocks /v3/signer-stats', (select avg(signer_stats_txns) from signer_30d),
        'NearBlocks /v3/accounts/v1.signer/stats/txns', (select avg(contract_stats_txns) from signer_30d),
        1.0, 'same_upstream'

    union all select 'mpc_threshold_latest_nearblocks_vs_contract', 'Chain Signatures signing threshold', null,
        'NearBlocks /v3/multichain/mpcs', (select nearblocks_threshold from mpc_threshold),
        'v1.signer contract state', (select contract_threshold from mpc_threshold),
        0.0, 'independent'

    union all select 'commits_52w_statistic_vs_default_branch', 'Commits over the 52 weeks read', 'near/nearcore',
        'GitHub weekly statistic', (select statistic from nearcore_commits),
        'GitHub commits list, default branch', (select default_branch from nearcore_commits),
        5.0, 'same_upstream'

    union all select 'tvl_latest_defillama_vs_nearblocks', 'NEAR chain TVL, USD', null,
        'DefiLlama', (select tvl_usd from {{ ref('fct_peer_daily') }} where chain_id = 'near' and tvl_usd is not null order by date_day desc limit 1),
        'NearBlocks', (select tvl_usd from {{ ref('stg_nearblocks__tvl_stats') }} where is_latest order by date_day desc limit 1),
        10.0, 'independent'

    union all select 'stablecoins_latest_chain_vs_assets', 'Stablecoins on NEAR, USD', null,
        'DefiLlama chain series', (select stablecoins_usd from {{ ref('fct_peer_daily') }} where chain_id = 'near' and stablecoins_usd is not null order by date_day desc limit 1),
        'DefiLlama, sum of assets', (select sum(circulating) from {{ ref('fct_stablecoin_assets') }}
            where chain_id = 'near' and snapshot_date = (select max(snapshot_date) from {{ ref('fct_stablecoin_assets') }})),
        3.0, 'same_upstream'

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
        when c.value_a = c.value_b then 'agree'
        else 'differs'
    end as status,
    n.explanation
from checks c
left join {{ ref('reconciliation_notes') }} n using (check_id)
