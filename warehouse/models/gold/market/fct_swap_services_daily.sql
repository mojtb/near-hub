-- NEAR Intents beside the other services that swap a token on one chain for a token on another, per UTC day.
-- The set and the rule that chose it are registry/swap_services.csv; docs/SOURCES.md says what was left out and why.
-- The figures are not one measure, and figure_kind says which a row is. swap_volume is the swaps a service settled:
-- THORChain and Chainflip from DefiLlama's `dexs` list, and NEAR Intents from fct_intents_daily, which is NEAR's own
-- all-route figure. bridge_volume is what was sent into a service on one chain to arrive on another, from DefiLlama's
-- `bridges` list, each transfer counted once: it includes a transfer that delivers the same token, which is not a swap.
-- NEAR's row repeats fct_intents_daily.volume_usd so that the comparison is one query; a test holds the two equal.
with services as (select * from {{ ref('swap_services') }}),

others as (
    select s.service_id, v.date_day, v.volume_usd, 'defillama' as volume_basis
    from {{ ref('stg_defillama__swap_service_volume') }} v
    join services s on s.llama_dimension = v.llama_dimension and s.llama_id = v.llama_id
    where v.is_latest
),

-- The registry's row without a DefiLlama list is NEAR Intents, read from this warehouse.
near as (
    select s.service_id, d.date_day, d.volume_usd, d.volume_basis
    from {{ ref('fct_intents_daily') }} d
    cross join (select service_id from services where llama_slug is null) s
    where d.volume_usd is not null
),

volumes as (
    select * from others
    union all
    select * from near
)

select
    v.date_day,
    v.service_id,
    s.service_name,
    v.volume_usd,
    s.figure_kind,
    s.what_it_counts,
    v.volume_basis,
    s.llama_slug is null as is_near_intents
from volumes v
join services s using (service_id)
