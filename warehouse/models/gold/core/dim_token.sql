-- Registry tokens plus decimals and a live price. Decimals come from the registry, where each was read from the
-- contract's ft_metadata; 1Click's figure is the fallback, and a data test holds the two to each other.
with oneclick as (
    select
        contract_address,
        min(decimals) as decimals,
        min(price_usd) as price_usd,
        min(coingecko_id) as coingecko_id,
        max(snapshot_date) as priced_on
    from {{ ref('stg_oneclick__tokens') }}
    where is_latest and blockchain = 'near' and contract_address is not null
    group by contract_address
)

select
    t.token_id,
    t.symbol,
    t.token_class,
    t.track_holders = 1 as tracks_holders,
    t.evidence_level,
    t.source_url,
    t.note,
    coalesce(t.decimals, o.decimals) as decimals,
    o.price_usd,
    o.coingecko_id,
    o.priced_on
from {{ ref('tokens') }} t
left join oneclick o on o.contract_address = t.token_id
