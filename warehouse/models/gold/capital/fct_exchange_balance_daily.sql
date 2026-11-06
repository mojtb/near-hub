-- Assets on NEAR in the wallets DefiLlama attributes to centralised exchanges, in USD, per exchange per day. DefiLlama lists
-- these wallets on its exchange pages and leaves them out of chain TVL; fct_protocol_tvl_daily leaves them out too, so here
-- they stand on their own. The figure is every asset in the listed wallets at DefiLlama's prices, so it is mostly NEAR and
-- moves with NEAR's price. Only wallets DefiLlama has labelled count: an exchange's unlabelled wallets are missing, and a
-- relabelling moves the whole series. History is fetched for the largest 25 protocols on NEAR, so a small exchange can
-- have a row in dim_protocol and no days here. DefiLlama can rewrite any of this history without notice.
with exchanges as (
    select protocol_id, protocol_slug, protocol_name
    from {{ ref('stg_defillama__protocols') }}
    where is_latest and category = 'CEX'
)

select
    t.date_day,
    t.protocol_id,
    e.protocol_slug as exchange_slug,
    e.protocol_name as exchange_name,
    t.tvl_usd as balance_usd
from {{ ref('stg_defillama__protocol_tvl') }} t
join exchanges e using (protocol_id)
where t.is_latest
