-- file_key is the DefiLlama dataType, such as dailyFees or dailyHoldersRevenue.
with files as ({{ bronze_files('defillama__intents_fees') }}),

points as (
    select snapshot_date, file_key as data_type, {{ explode("doc->'totalDataChart'") }} as p from files
),

typed as (
    select
        snapshot_date,
        data_type,
        {{ unix_day("p->>0") }} as date_day,
        cast(p->>1 as double) as value_usd
    from points
)

select *, {{ is_latest('data_type, date_day', 'value_usd') }} as is_latest
from typed
where date_day < snapshot_date
