-- Every claim in registry/claims.csv, for and against NEAR, measured against the warehouse: the value, the bar it was
-- set against, and whether the claim holds. "holds" means the claim as written is true of the data, so a bear claim
-- that holds counts against the thesis. A claim the data cannot settle stays in the table as not_testable.
-- Each claim's measurement is one select below, named by its claim_id; dim_claim.test says in words what it reads.
with settled as (
    select max(date_day) as d from {{ ref('fct_intents_daily') }} where not is_fee_revenue_provisional
),

months as (
    select *, row_number() over (order by month_start desc) as recency
    from {{ ref('fct_intents_unit_economics_monthly') }}
    where is_month_complete
),

dilution as (
    select n.* from {{ ref('fct_net_dilution_daily') }} n join settled s on n.date_day = s.d
),

intents_30d as (
    select i.* from {{ ref('fct_intents_daily') }} i, settled s where i.date_day > s.d - 30 and i.date_day <= s.d
),

signatures as (select * from {{ ref('fct_chain_signatures_daily') }}),
signatures_end as (select max(date_day) as d from signatures),

usage as (select * from {{ ref('fct_usage_quality_daily') }}),
usage_end as (select max(date_day) as d from usage),

peer as (select * from {{ ref('fct_peer_daily') }}),
peer_end as (select max(date_day) as d from peer where chain_id = 'near' and price_usd is not null and tvl_usd is not null),

returns_90d as (
    select p.chain_id, p.price_usd / b.price_usd - 1 as price_change
    from peer p
    join peer_end e on p.date_day = e.d
    join peer b on b.chain_id = p.chain_id and b.date_day = e.d - 90
),

cap_to_tvl as (
    select p.chain_id, p.market_cap_usd / p.tvl_usd as ratio
    from peer p join peer_end e on p.date_day = e.d
    where p.market_cap_usd is not null and p.tvl_usd > 0
),

multiples as (
    select m.chain_id, m.multiple, m.date_day
    from {{ ref('fct_valuation_multiples_daily') }} m
    where m.basis = 'app_fees'
      and m.date_day = (select max(date_day) from {{ ref('fct_valuation_multiples_daily') }} where basis = 'app_fees' and chain_id = 'near' and not is_provisional)
),

-- The last month in which the 1Click daily run has every day.
oneclick_month as (
    select max(month_start) as month_start from {{ ref('fct_intents_channel_economics_monthly') }} where is_month_complete
),

stablecoins as (
    select unnest(['USDT', 'USDC', 'DAI', 'USDT0', 'USDT0(DEPRECATED)', 'USDCx', 'xDAI', 'USDG', 'USD1', 'USDf', 'FRAX', 'EURe']) as symbol
),

pairs as (
    select
        p.amount_in_usd,
        p.origin_symbol = 'ZEC' or p.destination_symbol = 'ZEC' as touches_zec,
        p.origin_symbol in (select symbol from stablecoins) and p.destination_symbol in (select symbol from stablecoins) as is_stable_to_stable
    from {{ ref('fct_intents_1click_pair_daily') }} p
    join oneclick_month o on cast(date_trunc('month', p.date_day) as date) = o.month_start
    where p.is_in_daily_run
),

revenue_wallets as (select distinct account_id from {{ ref('fct_revenue_inflows_daily') }}),

validators as (
    select * from {{ ref('fct_validator_summary') }} where is_epoch_complete and approx_date_day is not null
),

newest_epoch as (select arg_max(validators, epoch_height) as validators, arg_max(approx_date_day, epoch_height) as d from validators),

measured as (
    select 'intents_is_the_fee_base' as claim_id,
        sum(total_30d_usd) filter (where protocol_slug = 'near-intents') / sum(total_30d_usd) as value,
        max(snapshot_date) as as_of_date
    from {{ ref('fct_protocol_fees_snapshot') }}
    where measure = 'fees' and category <> 'Chain'
      and snapshot_date = (select max(snapshot_date) from {{ ref('fct_protocol_fees_snapshot') }})

    union all
    select 'intents_revenue_is_growing',
        (a.revenue_usd / a.days_counted) / (b.revenue_usd / b.days_counted) - 1,
        last_day(a.month_start)
    from months a join months b on a.recency = 1 and b.recency = 4

    union all
    select 'capture_is_rising', a.capture_rate - b.capture_rate, last_day(a.month_start)
    from months a join months b on a.recency = 1 and b.recency = 7

    union all select 'offsets_are_material', offset_share, date_day from dilution
    union all select 'supply_is_shrinking', net_inflation_rate, date_day from dilution
    union all select 'issuance_is_over_five_times_offsets', 1 / nullif(offset_share, 0), date_day from dilution

    union all
    select 'a_doubling_of_volume_reaches_deflation_after_the_cut', breakeven_volume_multiple, as_of_date
    from {{ ref('fct_deflation_scenarios') }}
    where scenario_id = 'hsp029_end_state' and capture_case = 'measured'

    union all
    select 'most_volume_is_confidential',
        1 - sum(least(public_volume_usd, volume_usd)) / sum(volume_usd),
        max(date_day)
    from intents_30d
    where public_volume_usd is not null

    union all
    select 'chain_signatures_use_is_growing',
        avg(s.txns) filter (where s.date_day > e.d - 30) / avg(s.txns) filter (where s.date_day <= e.d - 180 and s.date_day > e.d - 210) - 1,
        max(e.d)
    from signatures s, signatures_end e

    union all
    select 'etf_took_in_more_than_issuance', arg_max(cumulative_flow_to_issuance_ratio, date_day), max(date_day)
    from {{ ref('fct_etf_absorption_daily') }}

    union all
    select 'governance_is_broad', arg_max(voters, proposal_id), arg_max(read_on, proposal_id)
    from {{ ref('fct_governance_proposals') }}
    where not is_test

    union all
    select 'near_beat_the_median_peer',
        max(price_change) filter (where chain_id = 'near') - median(price_change) filter (where chain_id <> 'near'),
        (select d from peer_end)
    from returns_90d

    union all select 'capture_stayed_above_a_fifth', min(capture_rate), last_day(max(month_start)) from months where recency <= 3
    union all select 'volume_stayed_above_2bn_a_month', min(volume_usd), last_day(max(month_start)) from months where recency <= 3

    union all
    select 'revenue_wallets_keep_their_near',
        (select -sum(f.amount_token) from {{ ref('fct_wallet_flows_daily') }} f
          where f.account_id in (select account_id from revenue_wallets) and f.direction = 'out'
            and not f.is_between_revenue_wallets and f.asset_id in ('native:near', 'nep141:wrap.near'))
        / sum(received_near),
        max(date_day)
    from {{ ref('fct_revenue_inflows_daily') }}

    union all
    select 'fees_depend_on_one_partner', arg_max(top_1_share, month_start), last_day(max(month_start))
    from {{ ref('fct_intents_concentration_monthly') }}
    where dimension = 'channel_fees' and is_month_complete

    union all select 'near_keeps_under_half_of_fees', capture_rate, last_day(month_start) from months where recency = 1

    union all
    select 'zcash_is_on_a_fifth_of_volume', sum(amount_in_usd) filter (where touches_zec) / sum(amount_in_usd), (select last_day(month_start) from oneclick_month)
    from pairs

    union all
    select 'volume_is_mostly_stablecoin_swaps', sum(amount_in_usd) filter (where is_stable_to_stable) / sum(amount_in_usd), (select last_day(month_start) from oneclick_month)
    from pairs

    union all
    select 'defi_on_near_is_thin',
        max(ratio) filter (where chain_id = 'near') / median(ratio) filter (where chain_id <> 'near'),
        (select d from peer_end)
    from cap_to_tvl

    union all
    select 'usage_is_falling',
        avg(u.txns_ex_batch_streams) filter (where u.date_day > e.d - 30) / avg(u.txns_ex_batch_streams) filter (where u.date_day <= e.d - 180 and u.date_day > e.d - 210) - 1,
        max(e.d)
    from usage u, usage_end e

    union all
    select 'sweat_carries_a_fifth_of_transactions', sum(u.sweat_relayer_txns) / sum(u.txns_ex_batch_streams), max(e.d)
    from usage u, usage_end e
    where u.date_day > e.d - 30

    union all
    select 'validator_set_is_shrinking',
        max(n.validators) / avg(v.validators) - 1,
        max(n.d)
    from validators v, newest_epoch n
    where v.approx_date_day between n.d - 65 and n.d - 55

    union all
    select 'near_is_dearer_than_the_median_peer',
        max(multiple) filter (where chain_id = 'near') / median(multiple) filter (where chain_id <> 'near'),
        max(date_day)
    from multiples

    union all
    select 'revenue_is_small_beside_trading', sum(i.revenue_usd) / sum(m.reported_spot_volume_usd), max(i.date_day)
    from intents_30d i
    join {{ ref('fct_market_daily') }} m using (date_day)
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
left join measured m using (claim_id)
