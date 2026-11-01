with files as ({{ bronze_files('defillama__chain_tvl') }}),

points as (
    select snapshot_date, file_key as llama_chain, {{ explode('doc') }} as p from files
),

typed as (
    select
        snapshot_date,
        llama_chain,
        {{ unix_day("p->>'date'") }} as date_day,
        cast(p->>'tvl' as double) as tvl_usd
    from points
)

select *, {{ is_latest('llama_chain, date_day', 'tvl_usd') }} as is_latest
from typed
where date_day < snapshot_date
