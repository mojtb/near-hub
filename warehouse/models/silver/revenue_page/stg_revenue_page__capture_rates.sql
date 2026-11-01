-- Point in time: capture rate per mechanism and window, published as fractions of gross fees.
with files as ({{ bronze_files('revenue_page__parsed') }}),

pairs as (
    select
        snapshot_date,
        doc->'captureRates' as rates,
        unnest(json_keys(doc->'captureRates')) as metric
    from files
)

select
    snapshot_date,
    case split_part(metric, '_', 2) when 'fe' then 'front_end' when 'b2b' then 'b2b_partners' when 'qi' then 'quote_improvement' end as mechanism,
    replace(metric, 'pp_' || split_part(metric, '_', 2) || '_', '') as time_window,
    cast(rates->>metric as double) as capture_rate
from pairs
where metric like 'pp\_%' escape '\'
