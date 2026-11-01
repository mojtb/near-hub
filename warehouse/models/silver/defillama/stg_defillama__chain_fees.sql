-- file_key is <chain>__<dataType>; dailyFees and dailyRevenue arrive as separate files.
with files as ({{ bronze_files('defillama__chain_fees') }}),

points as (
    select
        snapshot_date,
        split_part(file_key, '__', 1) as llama_chain,
        coalesce(nullif(split_part(file_key, '__', 2), ''), 'dailyFees') as data_type,
        {{ explode("doc->'totalDataChart'") }} as p
    from files
),

typed as (
    select
        snapshot_date,
        llama_chain,
        data_type,
        {{ unix_day("p->>0") }} as date_day,
        cast(p->>1 as double) as value_usd
    from points
)

select *, {{ is_latest('llama_chain, data_type, date_day', 'value_usd') }} as is_latest
from typed
where date_day < snapshot_date
