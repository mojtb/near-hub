-- Every claim in registry/claims.csv, for and against NEAR, measured against the warehouse: the value, the bar it was
-- set against, and whether the claim holds. "holds" means the claim as written is true of the data, so a bear claim
-- that holds counts against the thesis. A claim the data cannot settle stays in the table as not_testable.
-- Each claim's measurement is one select below, named by its claim_id; dim_claim.test says in words what it reads.
-- No measurement is scored twice: where the old set held several claims on one number, one is kept. A claim about
-- Intents reads three complete months together, because revenue is swept in lumps and one month can sit far from
-- the trend.
with settled as (
    select max(date_day) as d from {{ ref('fct_intents_daily') }} where not is_fee_revenue_provisional
),

months as (
    select *, row_number() over (order by month_start desc) as recency
    from {{ ref('fct_intents_unit_economics_monthly') }}
    where is_month_complete
),

peer_dex_monthly as (
    select cast(date_trunc('month', date_day) as date) as month_start, sum(dex_volume_usd) as dex_volume_usd
    from {{ ref('fct_peer_daily') }}
    where chain_id <> 'near'
    group by 1
),

-- The last three complete months, and the three before them.
quarters as (
    select
        m.recency <= 3 as is_newest,
        sum(m.volume_usd) as volume_usd,
        sum(m.fees_usd) as fees_usd,
        sum(m.revenue_usd) as revenue_usd,
        sum(p.dex_volume_usd) as peer_dex_volume_usd,
        max(m.month_start) as last_month
    from months m
    join peer_dex_monthly p using (month_start)
    where m.recency <= 6
    group by 1
),

-- The months in which the 1Click daily run has every day.
oneclick_months as (
    select month_start, row_number() over (order by month_start desc) as recency
    from (select distinct month_start from {{ ref('fct_intents_channel_economics_monthly') }} where is_month_complete)
),

oneclick_end as (select last_day(max(month_start)) as d from oneclick_months),

channels as (
    select c.referral, c.app_fee_usd, o.recency
    from {{ ref('fct_intents_channel_economics_monthly') }} c
    join oneclick_months o using (month_start)
    where o.recency <= 6
),

partner_fees as (
    select referral, sum(app_fee_usd) as app_fee_usd from channels where recency <= 3 group by 1
),

pairs as (
    select p.amount_in_usd, p.origin_symbol = 'ZEC' or p.destination_symbol = 'ZEC' as touches_zec
    from {{ ref('fct_intents_1click_pair_daily') }} p
    join oneclick_months o on cast(date_trunc('month', p.date_day) as date) = o.month_start and o.recency <= 3
    where p.is_in_daily_run
),

-- Three 30-day readings, 30 days apart, add up to 90 days: the newest 90 and the 90 before them. A year earlier the
-- revenue wallets had received nothing and issuance was twice as high, so against that base the claim could not fail.
offset_90d as (
    select
        n.date_day > s.d - 90 as is_newest,
        sum(n.burn_30d_near + n.revenue_inflow_30d_near) / sum(n.minted_30d_near) as offset_share
    from {{ ref('fct_net_dilution_daily') }} n, settled s
    where n.date_day in (s.d, s.d - 30, s.d - 60, s.d - 90, s.d - 120, s.d - 150)
    group by 1
),

-- Application fees by chain in the last three complete months over the three before. Quarters and not a year, by the
-- rule every claim about Intents follows: a year earlier NEAR's fees had barely started, so a yearly gain flatters it.
fees_quarters as (
    select
        p.chain_id,
        sum(p.fees_usd) filter (where p.date_day >= q.last_month - interval 2 month)
            / sum(p.fees_usd) filter (where p.date_day < q.last_month - interval 2 month) - 1 as fee_change,
        last_day(max(q.last_month)) as as_of_date
    from {{ ref('fct_peer_daily') }} p, (select last_month from quarters where is_newest) q
    where p.date_day >= q.last_month - interval 5 month and p.date_day < q.last_month + interval 1 month
    group by 1
),

multiples as (
    select m.chain_id, m.multiple, m.date_day
    from {{ ref('fct_valuation_multiples_daily') }} m
    where m.basis = 'app_fees'
      and m.date_day = (select max(date_day) from {{ ref('fct_valuation_multiples_daily') }} where basis = 'app_fees' and chain_id = 'near' and not is_provisional)
),

signers as (select date_day, distinct_signers from {{ ref('fct_chain_daily') }} where distinct_signers is not null),
signers_end as (select max(date_day) as d from signers),

revenue_wallets as (select distinct account_id from {{ ref('fct_revenue_inflows_daily') }}),

validators as (
    select * from {{ ref('fct_validator_summary') }} where is_epoch_complete and approx_date_day is not null
),

newest_epoch as (select arg_max(top_10_share, epoch_height) as top_10_share, arg_max(approx_date_day, epoch_height) as d from validators),

-- NEAR staked through the liquid staking tokens, by read. A read shows the first block of its day.
liquid_staking as (
    select snapshot_date, sum(delegated_near) as near_staked from {{ ref('fct_lst_snapshot') }} group by 1
),

liquid_staking_end as (select max(snapshot_date) as d from liquid_staking),

-- Dollar-pegged tokens held in NEAR Intents, as NEAR's dashboard splits the pool by asset, in the months that have every day.
intents_dollar_months as (
    select *, row_number() over (order by month_start desc) as recency
    from (
        select cast(date_trunc('month', date_day) as date) as month_start, avg(usd) as mean_usd
        from (
            select date_day, sum(tvl_usd) as usd
            from {{ ref('fct_dune_intents_tvl_asset_daily') }}
            where upper(symbol) in ('USDC', 'USDT', 'USDT0', 'USDCX', 'DAI', 'USDG', 'USAD', 'FRAX', 'USD1', 'USDE', 'PYUSD', 'USDS', 'USDF')
            group by 1
        )
        group by 1
        having count(*) = day(last_day(min(date_day)))
    )
),

measured as (
    select 'intents_is_gaining_share' as claim_id,
        (a.volume_usd / a.peer_dex_volume_usd) / (b.volume_usd / b.peer_dex_volume_usd) - 1 as value,
        last_day(a.last_month) as as_of_date
    from quarters a join quarters b on a.is_newest and not b.is_newest

    union all select 'volume_stayed_above_2bn_a_month', min(volume_usd), last_day(max(month_start)) from months where recency <= 3

    union all
    select 'capture_is_rising', a.revenue_usd / a.fees_usd - b.revenue_usd / b.fees_usd, last_day(a.last_month)
    from quarters a join quarters b on a.is_newest and not b.is_newest

    union all
    select 'fee_base_is_widening',
        count(*) filter (where recency <= 3) / nullif(count(*) filter (where recency > 3), 0)::double - 1,
        (select d from oneclick_end)
    from channels
    where app_fee_usd >= 10000 and referral <> '(none)'

    union all
    -- NEAR's own monthly revenue series against what the Intents contract paid its revenue wallets, counted on the day
    -- it arrived: native USDC at one dollar, NEAR at the transfer's value. DefiLlama's revenue is NEAR's own count of
    -- the same wallets, so its match with the transfers (dq_reconciliation) confirms that count and cannot fail here.
    select 'revenue_reaches_the_wallets',
        1 - (select sum(case when t.asset_id = 'nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1'
                             then t.amount_token else t.amount_usd end)
               from {{ ref('fct_wallet_transfers') }} t
              where t.account_id in (select account_id from revenue_wallets) and t.direction = 'in'
                and t.counterparty_id = 'intents.near'
                and t.asset_id in ('native:near', 'nep141:wrap.near',
                                   'nep141:17208628f84f5d6ad33f0da3bbbeb27ffcb398eac501a31bd6ad2011e36133a1'))
            / sum(revenue_usd),
        (select max(date_day) from {{ ref('fct_revenue_inflows_daily') }})
    from {{ ref('fct_revenue_page_monthly') }}

    union all
    select 'revenue_wallets_keep_their_near',
        (select -sum(f.amount_token) from {{ ref('fct_wallet_flows_daily') }} f
          where f.account_id in (select account_id from revenue_wallets) and f.direction = 'out'
            and not f.is_between_revenue_wallets and f.asset_id in ('native:near', 'nep141:wrap.near'))
        / sum(received_near),
        max(date_day)
    from {{ ref('fct_revenue_inflows_daily') }}

    union all
    select 'etf_took_in_more_than_issuance', arg_max(flow_to_issuance_30d_ratio, date_day), max(date_day)
    from {{ ref('fct_etf_absorption_daily') }}

    union all
    select 'offsets_are_rising', a.offset_share - b.offset_share, (select d from settled)
    from offset_90d a join offset_90d b on a.is_newest and not b.is_newest

    union all
    select 'unlocks_are_behind', 1 - arg_max(circulating_share_of_total, date_day), max(date_day)
    from {{ ref('fct_circulating_supply_daily') }}

    union all
    select 'a_doubling_of_volume_reaches_deflation_after_the_cut', breakeven_volume_multiple, as_of_date
    from {{ ref('fct_deflation_scenarios') }}
    where scenario_id = 'hsp029_end_state' and capture_case = 'measured'

    union all
    select 'near_fees_outgrew_every_peer',
        max(fee_change) filter (where chain_id = 'near') - max(fee_change) filter (where chain_id <> 'near'),
        max(as_of_date)
    from fees_quarters

    union all
    select 'near_is_dearer_than_the_median_peer',
        max(multiple) filter (where chain_id = 'near') / median(multiple) filter (where chain_id <> 'near'),
        max(date_day)
    from multiples

    union all
    select 'fees_depend_on_one_partner', max(app_fee_usd) / sum(app_fee_usd), (select d from oneclick_end)
    from partner_fees

    union all
    select 'zcash_is_on_a_fifth_of_volume', sum(amount_in_usd) filter (where touches_zec) / sum(amount_in_usd), (select d from oneclick_end)
    from pairs

    union all
    -- Signers and not transactions: transactions without the batch streams were only lower with the Sweat relayer in
    -- the count, and that relayer is due to stop, so they did not say what the claim says.
    select 'usage_is_falling',
        avg(u.distinct_signers) filter (where u.date_day > e.d - 30) / avg(u.distinct_signers) filter (where u.date_day <= e.d - 180 and u.date_day > e.d - 210) - 1,
        max(e.d)
    from signers u, signers_end e

    union all
    -- The sample prompt's hypothesis, read on weeks cut on Mondays: the largest link with volume one or two weeks ahead.
    select 'intents_volume_leads_usage', max(correlation), max(last_week) + 6
    from {{ ref('fct_usage_lead_correlations') }}
    where week_shift_days = 0 and leader = 'intents_volume' and lead_weeks in (1, 2)

    union all
    -- The ten largest pools' share and not the number of pools: the pools that left in 60 days held under 1% of the
    -- stake, and the count moves by a dozen between two epochs of one day, so it did not say who could stop the chain.
    select 'ten_pools_hold_a_third', top_10_share, d
    from newest_epoch

    union all
    select 'liquid_staking_is_shrinking', max(n.near_staked) / max(y.near_staked) - 1, max(e.d)
    from liquid_staking_end e
    join liquid_staking n on n.snapshot_date = e.d
    join liquid_staking y on y.snapshot_date = e.d - interval 365 day

    union all
    select 'dollars_are_arriving_in_intents',
        avg(mean_usd) filter (where recency <= 3) / avg(mean_usd) filter (where recency between 4 and 6) - 1,
        last_day(max(month_start))
    from intents_dollar_months
    where recency <= 6
)

select
    c.claim_id,
    c.side,
    c.claim,
    m.value,
    c.comparison,
    c.threshold,
    case
        when c.comparison is null then 'not_testable'
        when m.value is null then 'not_measured'
        when c.comparison = '>=' and m.value >= c.threshold then 'holds'
        when c.comparison = '<=' and m.value <= c.threshold then 'holds'
        else 'fails'
    end as status,
    m.as_of_date
from {{ ref('dim_claim') }} c
-- Each value is rounded to ten decimals: a sum over many days is not the same to its last digit on every build, and
-- a rebuild must give the file that was committed.
left join (select claim_id, round(value, 10) as value, as_of_date from measured) m using (claim_id)
