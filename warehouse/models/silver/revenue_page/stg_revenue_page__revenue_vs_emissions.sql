-- Year-to-date running totals published by NEAR: emissions and revenue in NEAR, percentages of reference supply.
with files as ({{ bronze_files('revenue_page__parsed') }}),

rows as (
    select snapshot_date, {{ explode("doc->'absoluteRevEmissions'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'emissionsNear' as double) as emissions_ytd_near,
        cast(r->>'revenueNear' as double) as revenue_ytd_near,
        cast(r->>'referenceSupplyNear' as double) as reference_supply_near,
        cast(r->>'grossPct' as double) as gross_issuance_pct,
        cast(r->>'netPct' as double) as net_issuance_pct,
        cast(r->>'offsetPct' as double) as offset_pct
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
