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

-- A dashboard reading is taken in a browser on request, so it stands still while the daily series move on. Its all-time tiles are
-- therefore compared with the other source on the reading's last full day, which is what the tiles covered.
dune_day as (
    select max(snapshot_date) - 1 as d from {{ ref('fct_intents_dashboard_readings') }}
),

dune_assets as (select * from {{ ref('fct_dune_intents_asset_daily') }}),
dune_chains as (select * from {{ ref('fct_dune_intents_chain_daily') }}),

-- The latest full month in which at least 99% of volume was public. In such a month NearBlocks, which reads the
-- public chain, and NEAR's dashboard, which counts every route, describe nearly the same swaps, so they can be
-- held against each other. The second month asks for 85%: it is the latest one in which bridged Bitcoin, which
-- NearBlocks lists under near, can be checked against the dashboard's Bitcoin.
public_months as (
    select
        cast(date_trunc('month', date_day) as date) as m,
        sum(least(public_volume_usd, volume_usd)) / sum(volume_usd) as public_part
    from intents
    where public_volume_usd is not null and date_day in (select date_day from dune_chains)
    group by 1
    having count(*) = day(last_day(min(date_day)))
),

public_month as (select max(m) as m from public_months where public_part >= 0.99),
mostly_public_month as (select max(m) as m from public_months where public_part >= 0.85),

dune_chain_month as (
    select blockchain, sum(volume_usd) as usd
    from dune_chains, public_month
    where cast(date_trunc('month', date_day) as date) = m
    group by blockchain
    order by 2 desc, 1
    limit 6
),

nearblocks_chain_month as (
    select blockchain, sum(volume_usd) as usd
    from {{ ref('fct_intents_chain_daily') }}, public_month
    where cast(date_trunc('month', date_day) as date) = m
    group by blockchain
),


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

etf_seed as (select date_day from {{ ref('fct_etf_nrr_daily') }} where flow_basis = 'seed_capital'),

-- The NEAR price a day's NAV implies is NAV over the NEAR behind one share. Bitwise strikes NAV at a US close,
-- so it is held to the day's whole range on Coinbase, not to a UTC close.
etf_nav_days as (
    select d.date_day, d.nav_usd / d.near_per_share between cb.low_usd and cb.high_usd as is_inside
    from {{ ref('fct_etf_nrr_daily') }} d
    join (select date_day, low_usd, high_usd from {{ ref('stg_coinbase__candles') }} where is_latest) cb using (date_day)
    where d.flow_basis <> 'seed_capital' and d.nav_usd is not null and d.near_per_share is not null
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

-- Both sides are the nightly snapshot's reads, minutes apart. fct_mpc_state prefers the read at the day's first block,
-- hours earlier, so on a day the threshold changed it could differ from NearBlocks without either being wrong.
mpc_threshold as (
    select s.snapshot_date, cast(s.result->'Running'->'parameters'->>'threshold' as integer) as contract_threshold,
        max(o.threshold) as nearblocks_threshold
    from {{ ref('stg_rpc__contract_views') }} s
    join {{ ref('stg_nearblocks__mpc_operators') }} o using (snapshot_date)
    where s.contract = 'v1.signer' and s.method = 'state'
    group by all
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

-- fct_token_price_daily takes ETH and SOL from CoinMetrics, as fct_peer_daily does, so holding those two tables against
-- each other would compare a series with itself. The other route this warehouse has for the two is DefiLlama's price
-- of each peer chain's token, which no gold table uses where CoinMetrics has a value. Both are the close of the UTC day.
token_price_30d as (
    select t.symbol, avg(t.price_usd) as price_usd_table, avg(d.price_usd) as price_usd_defillama
    from {{ ref('fct_token_price_daily') }} t
    join {{ ref('peers') }} pe on pe.coinmetrics_asset = t.source_asset_id
    join {{ ref('stg_defillama__peer_price') }} d on d.coin_id = pe.coingecko_id and d.date_day = t.date_day
    where t.price_source = 'coinmetrics' and d.is_latest
      and t.date_day > (select max(date_day) from {{ ref('fct_token_price_daily') }}) - 30
    group by t.symbol
),

-- The Intents pool read from the chain at month ends, beside NEAR's dashboard on the same days. The chain side is
-- intents.near's balance at the first block after the day; the dashboard's figure for a day is the pool as that day ends.
-- Only wNEAR and the dollar tokens are compared: the table's other assets are in token units and need a price.
pool_month_ends as (
    select date_day, token_class, sum(amount_token) as chain_amount
    from {{ ref('fct_intents_pool_chain_monthly') }}
    where is_month_end and token_class in ('native_wrapped', 'stablecoin')
    group by date_day, token_class
),

-- The dashboard gives wNEAR in dollars at a price of its own, so its figure over the chain's balance is the price it
-- used. The two fit if that is a price NEAR traded at on the day.
pool_wnear_days as (
    select c.date_day, t.tvl_usd / c.chain_amount between k.low_usd and k.high_usd as is_inside
    from pool_month_ends c
    join {{ ref('fct_dune_intents_tvl_asset_daily') }} t on t.date_day = c.date_day and t.symbol = 'wNEAR'
    join {{ ref('stg_coinbase__candles') }} k on k.date_day = c.date_day and k.is_latest
    where c.token_class = 'native_wrapped' and c.chain_amount > 0
),

-- Dollar tokens are matched by symbol: the dashboard's assets with a symbol the chain reading counts as a dollar. The
-- dashboard's series has no value for USDT0 before a day in March 2026, though the pool already held it, so the month
-- ends before that day and from it are compared apart. In each group the month end where chain and dashboard differ
-- most is the one shown, so a row agrees only if every month end of its group does.
pool_dashboard_dollars as (
    select date_day, sum(tvl_usd) as dashboard_usd
    from {{ ref('fct_dune_intents_tvl_asset_daily') }}
    where upper(symbol) in (select upper(symbol) from {{ ref('fct_intents_pool_chain_monthly') }} where token_class = 'stablecoin')
    group by date_day
),

pool_dashboard_usdt0_from as (
    select min(date_day) as d from {{ ref('fct_dune_intents_tvl_asset_daily') }} where upper(symbol) = 'USDT0' and tvl_usd > 0
),

-- The pool's other main assets, valued on chain: each asset's balances at the day's independent price beside the
-- dashboard's dollar value of the same asset on the same day. An asset counts on a day only when every token of it
-- has a price. The dashboard does not say at what hour it values an asset, so a day's move in price sits in the gap.
pool_priced_assets as (
    select c.date_day, c.dashboard_symbol as symbol, sum(c.value_usd) as chain_usd, max(d.tvl_usd) as dashboard_usd
    from {{ ref('fct_intents_pool_chain_monthly') }} c
    join {{ ref('fct_dune_intents_tvl_asset_daily') }} d on d.symbol = c.dashboard_symbol and d.date_day = c.date_day
    where c.token_class = 'other'
    group by 1, 2
    having count(c.value_usd) = count(*) and max(d.tvl_usd) > 0
),

pool_priced_newest as (
    select * from pool_priced_assets where date_day = (select max(date_day) from pool_priced_assets)
),

-- All the priced assets together at each month end, and the month end where chain and dashboard are furthest apart.
pool_priced_widest_gap as (
    select date_day, sum(chain_usd) as chain_usd, sum(dashboard_usd) as dashboard_usd
    from pool_priced_assets
    where date_day = last_day(date_day)
    group by 1
    order by abs(sum(chain_usd) / sum(dashboard_usd) - 1) desc
    limit 1
),

pool_dollars_widest_gap as (
    select *
    from (
        select c.date_day, coalesce(c.date_day >= u.d, false) as dashboard_has_usdt0, c.chain_amount as chain_usd, d.dashboard_usd,
            row_number() over (
                partition by coalesce(c.date_day >= u.d, false)
                order by abs(c.chain_amount - d.dashboard_usd) / greatest(c.chain_amount, d.dashboard_usd) desc, c.date_day desc
            ) as widest
        from pool_month_ends c
        join pool_dashboard_dollars d using (date_day)
        cross join pool_dashboard_usdt0_from u
        where c.token_class = 'stablecoin'
    )
    where widest = 1
),

-- NEAR's public BigQuery dataset against NearBlocks and the archival node, on the days both hold. Only days BigQuery had
-- loaded whole when it was read are compared. The two count from different copies of the chain: NearBlocks from its own
-- indexer, BigQuery from NEAR's lakehouse loader.
bq_days as (
    select
        b.date_day, b.txns as bq_txns, n.txns as nb_txns, b.signers as bq_signers, n.active_signers as nb_signers,
        b.blocks as bq_blocks, n.blocks as nb_blocks, b.transactions_table_rows, b.total_supply_near as bq_supply
    from {{ ref('fct_bigquery_chain_daily') }} b
    join {{ ref('fct_chain_daily') }} n using (date_day)
    where b.is_day_complete
),

bq_txn_days as (select * from bq_days where bq_txns is not null and nb_txns is not null),
bq_signer_days as (select * from bq_days where bq_signers is not null and nb_signers is not null),
bq_block_days as (select * from bq_days where bq_blocks is not null and nb_blocks is not null),
bq_last_day as (select max(date_day) as d from bq_days where bq_supply is not null),

-- Total supply at the day's last block in BigQuery against the next day's first block on the archival node, every day.
bq_supply_days as (
    select b.date_day, b.bq_supply, s.total_supply_near as chain_supply
    from bq_days b
    join {{ ref('fct_supply_daily') }} s using (date_day)
    where b.bq_supply is not null and s.total_supply_near is not null
),

-- Every day since genesis: the rows BigQuery records in the transactions table's daily partition against NearBlocks.
bq_all_days as (
    select b.date_day, b.transactions_table_rows as bq_rows, n.txns as nb_txns
    from {{ ref('fct_bigquery_chain_daily') }} b
    join {{ ref('fct_chain_daily') }} n using (date_day)
    where b.transactions_table_rows is not null and n.txns is not null
),

-- Actions by kind against the NearBlocks counts they correspond to. A relayed request is a DELEGATE_ACTION: its actions
-- are NearBlocks' meta-transactions and the accounts it was sent to are the accounts a relayer signed for.
bq_action_days as (
    select
        a.date_day,
        max(case when a.action_kind = 'DELEGATE_ACTION' then a.actions end) as bq_meta_txns,
        max(case when a.action_kind = 'DELEGATE_ACTION' then a.receivers end) as bq_meta_accounts,
        max(case when a.action_kind = 'DELETE_ACCOUNT' then a.receivers end) as bq_deleted_accounts,
        max(case when a.action_kind = 'FUNCTION_CALL' then a.receivers end) as bq_contracts_called,
        max(n.meta_txns) as nb_meta_txns,
        max(n.meta_accounts) as nb_meta_accounts,
        max(n.deleted_accounts) as nb_deleted_accounts,
        max(n.active_contracts) as nb_active_contracts
    from {{ ref('fct_bigquery_action_daily') }} a
    join {{ ref('fct_chain_daily') }} n using (date_day)
    group by a.date_day
),

bq_intents_callers as (
    select b.date_day, b.callers as bq_callers, c.unique_callers as nb_callers
    from {{ ref('fct_bigquery_contract_daily') }} b
    join {{ ref('fct_contract_daily') }} c on c.date_day = b.date_day and c.account_id = b.contract_id
    where b.contract_id = 'intents.near' and c.unique_callers is not null
),

-- NEAR's own circulating supply against this warehouse's. The two are computed at different blocks of the day, so what
-- is compared is the locked amount each takes off total supply, which does not move with the day's issuance.
bq_locked as (
    select b.date_day, b.not_circulating_near as bq_locked, c.lockup_locked_near + c.foundation_locked_near as chain_locked
    from {{ ref('fct_bigquery_circulating_supply_daily') }} b
    join {{ ref('fct_circulating_supply_daily') }} c using (date_day)
    where b.not_circulating_near is not null
),

bq_locked_last as (select max(date_day) as d from bq_locked),

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

    union all select 'intents_volume_dune_assets_vs_defillama', 'Intents volume per asset over the 30 days to the latest Dune reading''s last day, USD', null,
        'Dune public page, sum of assets', (select sum(volume_usd) from dune_assets where date_day > (select max(date_day) from dune_assets) - 30),
        'DefiLlama, same days', (select sum(volume_usd) from llama_volume where date_day in (select date_day from dune_assets where date_day > (select max(date_day) from dune_assets) - 30)),
        1.0, 'same_upstream'

    union all select 'intents_volume_30d_dune_assets_vs_tile', 'Intents trailing 30-day volume, USD', null,
        'Dune public page, sum of assets', (select sum(volume_usd) from dune_assets where date_day > (select max(date_day) from dune_assets) - 30),
        'Dune public page, all scopes', (select value_usd from dune where metric = 'volume_30d' and scope = 'all'),
        1.0, 'same_upstream'

    union all select 'intents_volume_dune_assets_vs_page', 'Intents volume on every day read per asset, USD', null,
        'Dune public page, sum of assets', (select sum(volume_usd) from dune_assets),
        'revenue.near.org, same days', (select sum(volume_usd) from page_volume where date_day in (select date_day from dune_assets)),
        1.0, 'same_upstream'

    union all select 'intents_volume_dune_chains_vs_page', 'Intents volume on every day read per blockchain, USD', null,
        'Dune public page, sum of blockchains', (select sum(volume_usd) from dune_chains),
        'revenue.near.org, same days', (select sum(volume_usd) from page_volume where date_day in (select date_day from dune_chains)),
        1.0, 'same_upstream'

    union all select 'intents_swaps_public_month_nearblocks_vs_dune', 'Swaps in the latest month that was at least 99% public', null,
        'NearBlocks, public swaps', (select sum(public_swaps) from intents, public_month where cast(date_trunc('month', date_day) as date) = m),
        'Dune public page, all routes', (select sum(swaps) from {{ ref('fct_dune_intents_swaps_daily') }}, public_month where cast(date_trunc('month', date_day) as date) = m),
        2.0, 'independent'

    union all select 'intents_chain_volume_public_month_nearblocks_vs_dune', 'Intents volume per blockchain in the latest month that was at least 99% public, USD', d.blockchain,
        'NearBlocks, public routes', n.usd,
        'Dune public page, all routes', d.usd,
        2.0, 'independent'
    from dune_chain_month d left join nearblocks_chain_month n using (blockchain)

    union all select 'intents_bitcoin_volume_nearblocks_vs_dune', 'Bitcoin volume in the latest month that was at least 85% public, USD', null,
        'NearBlocks, public routes, with Bitcoin bridged to NEAR counted as Bitcoin', (select sum(volume_usd) from {{ ref('fct_intents_chain_daily') }}, mostly_public_month where blockchain = 'btc' and cast(date_trunc('month', date_day) as date) = m),
        'Dune public page, all routes', (select sum(volume_usd) from dune_chains, mostly_public_month where blockchain = 'btc' and cast(date_trunc('month', date_day) as date) = m),
        15.0, 'independent'

    union all select 'intents_wnear_dune_tvl_vs_holdings', 'wNEAR held in NEAR Intents on the latest Dune reading''s last day, NEAR', null,
        'Dune public page, wNEAR TVL over the day''s price', (select t.tvl_usd / p.price_usd from {{ ref('fct_dune_intents_tvl_asset_daily') }} t join {{ ref('fct_market_daily') }} p using (date_day), dune_day where t.symbol = 'wNEAR' and t.date_day = d),
        'intents.near''s wNEAR balance on chain, read that day', (select max(amount_token) from {{ ref('fct_wallet_holdings') }}, dune_day where account_id = 'intents.near' and symbol = 'wNEAR' and snapshot_date = d),
        5.0, 'independent'

    union all select 'intents_pool_wnear_month_ends_dune_vs_coinbase_range', 'Month ends where the dashboard''s wNEAR value over intents.near''s wNEAR balance on chain is a NEAR price inside Coinbase''s range for that day', null,
        'Month ends inside Coinbase''s low and high', (select count(*) filter (where is_inside) from pool_wnear_days),
        'Month ends compared', (select nullif(count(*), 0) from pool_wnear_days),
        0.0, 'independent'

    union all select 'intents_pool_dollars_month_ends_chain_vs_dune', 'Dollar tokens held in NEAR Intents at the month end where chain and dashboard differ most, USD',
        case when dashboard_has_usdt0 then 'month ends since the dashboard has carried USDT0' else 'month ends before the dashboard carried USDT0' end,
        'intents.near''s balances on chain at one dollar each, at the first block after ' || cast(date_day as varchar), chain_usd,
        'Dune public page, TVL of the assets with those symbols on that day', dashboard_usd,
        3.0, 'independent'
    from pool_dollars_widest_gap

    union all select 'intents_pool_asset_newest_day_chain_vs_dune', 'Value of one main asset held in NEAR Intents on the newest day read from the chain, USD', symbol,
        'intents.near''s balances on chain at the first block after ' || cast(date_day as varchar) || ', at the asset''s price for that day', chain_usd,
        'Dune public page, TVL of the asset on that day', dashboard_usd,
        5.0, 'independent'
    from pool_priced_newest

    union all select 'intents_pool_priced_assets_month_ends_chain_vs_dune', 'The priced main assets held in NEAR Intents, together, at the month end where chain and dashboard differ most, USD', null,
        'intents.near''s balances on chain at the first block after ' || cast(date_day as varchar) || ', at each asset''s price for that day', chain_usd,
        'Dune public page, TVL of the same assets on that day', dashboard_usd,
        5.0, 'independent'
    from pool_priced_widest_gap

    union all select 'intents_revenue_all_time_defillama_vs_wallets', 'Intents revenue received by the wallets, USD', null,
        'DefiLlama, sum of daily', (select sum(revenue_usd) from intents),
        -- Both sides add up what the same three wallets received and value it at the day's close, so this confirms the
        -- count of receipts and says nothing about NEAR's own revenue series: marked as not independent.
        'Wallet transfers, the same wallets and method', (select sum(received_usd) from inflows),
        3.0, 'same_upstream'

    union all select 'intents_revenue_all_time_defillama_vs_page_monthly', 'Intents revenue received by the wallets, USD', null,
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

    union all select 'intents_pool_dune_total_vs_chain', 'Value held in NEAR Intents, public and confidential, USD', null,
        'Dune public page, on the reading''s last day', (select sum(tvl_usd) from {{ ref('fct_dune_intents_tvl_daily') }}, dune_day where date_day = d),
        'intents.near on chain, the tokens the warehouse can price, on the read after that day',
        (select sum(value_usd) from {{ ref('fct_wallet_holdings') }}, dune_day
          where account_id = 'intents.near'
            and snapshot_date = least(d + 1, (select max(snapshot_date) from {{ ref('fct_wallet_holdings') }}))),
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

    union all select 'token_price_30d_coinmetrics_vs_defillama', 'Mean close over 30 days of a pool asset priced in fct_token_price_daily, USD', symbol,
        'fct_token_price_daily, from CoinMetrics', price_usd_table,
        'DefiLlama', price_usd_defillama,
        0.5, 'independent'
    from token_price_30d

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

    union all select 'etf_nrr_near_delivered_chain_vs_fund', 'NEAR delivered to the Bitwise NEAR ETF since its first trading day', null,
        'Chain, NEAR moved into the listed wallets after the seed',
        (select sum(c.moved_near) from etf_chain c where c.date_day > (select date_day from etf_seed)),
        'Shares created less redeemed, each at that day''s NEAR per share',
        (select sum(flow_near) from {{ ref('fct_etf_nrr_daily') }} where flow_basis <> 'seed_capital'),
        1.0, 'independent'

    union all select 'etf_nrr_nav_vs_coinbase_range', 'Trading days the Bitwise NEAR ETF''s NAV implies a NEAR price inside Coinbase''s range for that day', null,
        'Days inside Coinbase''s low and high', (select count(*) filter (where is_inside) from etf_nav_days),
        'Trading days compared', (select count(*) from etf_nav_days),
        0.0, 'independent'

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
    union all select 'chain_txns_bigquery_vs_nearblocks', 'Transactions over the days both sources hold', null,
        'BigQuery public dataset, count of the transactions table', (select sum(bq_txns) from bq_txn_days),
        'NearBlocks', (select sum(nb_txns) from bq_txn_days),
        0.1, 'independent'

    union all select 'chain_txns_days_equal_bigquery_vs_nearblocks', 'Days on which both sources count exactly the same transactions', null,
        'days with equal counts', (select count(*) from bq_txn_days where bq_txns = nb_txns),
        'days both sources hold', (select count(*) from bq_txn_days),
        1.0, 'independent'

    union all select 'chain_signers_bigquery_vs_nearblocks', 'Distinct signers per day, summed over the days both sources hold', null,
        'BigQuery public dataset, distinct signer_account_id', (select sum(bq_signers) from bq_signer_days),
        'NearBlocks /v1 active accounts', (select sum(nb_signers) from bq_signer_days),
        0.5, 'independent'

    union all select 'chain_signers_days_equal_bigquery_vs_nearblocks', 'Days on which both sources count exactly the same distinct signers', null,
        'days with equal counts', (select count(*) from bq_signer_days where bq_signers = nb_signers),
        'days both sources hold', (select count(*) from bq_signer_days),
        1.0, 'independent'

    union all select 'chain_blocks_bigquery_vs_nearblocks', 'Blocks over the days both sources hold', null,
        'BigQuery public dataset, count of the blocks table', (select sum(bq_blocks) from bq_block_days),
        'NearBlocks', (select sum(nb_blocks) from bq_block_days),
        0.1, 'independent'

    union all select 'chain_txns_bigquery_count_vs_partition_rows', 'Transactions over the days counted, against the rows BigQuery records for the same daily partitions', null,
        'BigQuery, count of the transactions table', (select sum(bq_txns) from bq_days where bq_txns is not null and transactions_table_rows is not null),
        'BigQuery, rows in the table''s partitions', (select sum(transactions_table_rows) from bq_days where bq_txns is not null and transactions_table_rows is not null),
        0.01, 'same_upstream'

    union all select 'total_supply_latest_bigquery_vs_chain', 'Total supply at the end of the newest day BigQuery holds whole, NEAR', null,
        'BigQuery public dataset, the day''s last block', (select bq_supply from bq_days, bq_last_day where date_day = d),
        'archival node, the next day''s first block', (select total_supply_near from {{ ref('fct_supply_daily') }}, bq_last_day where date_day = d),
        0.01, 'independent'
    union all select 'chain_txns_all_history_bigquery_vs_nearblocks', 'Transactions since genesis, over every day both sources hold', null,
        'BigQuery, rows in the transactions table''s daily partitions', (select sum(bq_rows) from bq_all_days),
        'NearBlocks', (select sum(nb_txns) from bq_all_days),
        0.1, 'independent'

    union all select 'chain_txns_days_equal_all_history_bigquery_vs_nearblocks', 'Days since genesis on which both sources count exactly the same transactions', null,
        'days with equal counts', (select count(*) from bq_all_days where bq_rows = nb_txns),
        'days both sources hold', (select count(*) from bq_all_days),
        1.0, 'independent'

    union all select 'meta_txns_bigquery_vs_nearblocks', 'Relayed (meta) transactions over the days both sources hold', null,
        'BigQuery, DELEGATE_ACTION actions', (select sum(bq_meta_txns) from bq_action_days where bq_meta_txns is not null and nb_meta_txns is not null),
        'NearBlocks meta-transactions', (select sum(nb_meta_txns) from bq_action_days where bq_meta_txns is not null and nb_meta_txns is not null),
        0.1, 'independent'

    union all select 'meta_accounts_bigquery_vs_nearblocks', 'Accounts a relayer signed for per day, summed over the days both sources hold', null,
        'BigQuery, distinct receivers of DELEGATE_ACTION', (select sum(bq_meta_accounts) from bq_action_days where bq_meta_accounts is not null and nb_meta_accounts is not null),
        'NearBlocks meta accounts', (select sum(nb_meta_accounts) from bq_action_days where bq_meta_accounts is not null and nb_meta_accounts is not null),
        0.5, 'independent'

    union all select 'deleted_accounts_bigquery_vs_nearblocks', 'Accounts deleted over the days both sources hold', null,
        'BigQuery, distinct receivers of DELETE_ACCOUNT per day', (select sum(bq_deleted_accounts) from bq_action_days where bq_deleted_accounts is not null and nb_deleted_accounts is not null),
        'NearBlocks /v1 deleted accounts', (select sum(nb_deleted_accounts) from bq_action_days where bq_deleted_accounts is not null and nb_deleted_accounts is not null),
        5.0, 'independent'

    union all select 'active_contracts_bigquery_vs_nearblocks', 'Contracts active per day, mean over the days both sources hold', null,
        'BigQuery, distinct accounts that received a function call', (select avg(bq_contracts_called) from bq_action_days where bq_contracts_called is not null and nb_active_contracts is not null),
        'NearBlocks active contracts', (select avg(nb_active_contracts) from bq_action_days where bq_contracts_called is not null and nb_active_contracts is not null),
        5.0, 'independent'

    union all select 'intents_callers_bigquery_vs_nearblocks', 'Distinct callers of intents.near per day, summed over the days both sources hold', null,
        'BigQuery, distinct senders of a receipt calling it', (select sum(bq_callers) from bq_intents_callers),
        'NearBlocks unique callers', (select sum(nb_callers) from bq_intents_callers),
        1.0, 'independent'

    union all select 'locked_supply_latest_bigquery_vs_chain', 'NEAR still locked, on the newest day both hold: what each takes off total supply to get circulating supply', null,
        'NEAR''s circulating_supply table in BigQuery', (select bq_locked from bq_locked, bq_locked_last where date_day = d),
        'this warehouse, every lockup contract read on chain', (select chain_locked from bq_locked, bq_locked_last where date_day = d),
        0.1, 'independent'

    union all select 'locked_supply_days_within_bigquery_vs_chain', 'Days on which the two locked amounts are within 0.1% of each other', null,
        'days within 0.1%', (select count(*) from bq_locked where abs(bq_locked - chain_locked) <= 0.001 * chain_locked),
        'days NEAR''s table holds a figure', (select count(*) from bq_locked),
        1.0, 'independent'
    union all select 'chain_blocks_days_equal_bigquery_vs_nearblocks', 'Days on which both sources count exactly the same blocks', null,
        'days with equal counts', (select count(*) from bq_block_days where bq_blocks = nb_blocks),
        'days both sources hold', (select count(*) from bq_block_days),
        1.0, 'independent'

    union all select 'total_supply_days_within_bigquery_vs_chain', 'Days on which the two total supplies are within one part in a million', null,
        'days within one part in a million', (select count(*) from bq_supply_days where abs(bq_supply - chain_supply) <= 1e-6 * chain_supply),
        'days both sources hold', (select count(*) from bq_supply_days),
        0.5, 'independent'
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
    n.explanation,
    n.gap_kind
from checks c
left join {{ ref('reconciliation_notes') }} n using (check_id)
