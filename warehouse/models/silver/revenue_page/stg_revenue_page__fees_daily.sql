with files as ({{ bronze_files('revenue_page__parsed') }}),

rows as (
    select snapshot_date, {{ explode("doc->'totalFeesSeries'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date_at', 10) as date) as date_day,
        cast(r->>'total_fees_near' as double) as total_fees_near,
        cast(r->>'protocol_fee_near' as double) as protocol_fee_near,
        cast(r->>'intents_revenue_near' as double) as intents_revenue_near,
        cast(r->>'burn_revenue_near' as double) as burn_revenue_near,
        cast(r->>'fees_usd' as double) as fees_usd,
        cast(r->>'cumulative_fees_near' as double) as cumulative_fees_near,
        cast(r->>'cumulative_fees_usd' as double) as cumulative_fees_usd
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
