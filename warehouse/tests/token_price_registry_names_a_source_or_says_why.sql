-- registry/token_prices.csv holds two kinds of row. A priced asset names its source, the source's own id, the kind of
-- price, the first day of its series and what the price is, and the kind follows from the source: CoinMetrics gives a
-- reference rate and DefiLlama an aggregator's price. An asset with no independent public price series names none of
-- these and says in its note what was asked and where. Nothing in between is allowed, so a row can never be half filled
-- in and priced by accident.
select symbol, price_source, price_kind, 'a priced asset must name its series, kind, first day and what the price is' as fault
from {{ ref('token_prices') }}
where price_source is not null
    and (source_asset_id is null or price_kind is null or first_price_day is null or what_the_price_is is null)

union all

select symbol, price_source, price_kind, 'kind does not follow the source' as fault
from {{ ref('token_prices') }}
where price_source is not null
    and (price_source, price_kind) not in (('coinmetrics', 'reference_rate'), ('defillama', 'aggregator_price'))

union all

select symbol, price_source, price_kind, 'an asset without a source must name no series, and its note must say why' as fault
from {{ ref('token_prices') }}
where price_source is null
    and (source_asset_id is not null or price_kind is not null or first_price_day is not null or what_the_price_is is not null or note is null)

union all

select symbol, null, null, 'a symbol may have one row' as fault
from {{ ref('token_prices') }}
group by symbol
having count(*) > 1
