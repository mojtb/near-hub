with files as ({{ bronze_files('defillama__stablecoin_chain') }}),

points as (
    select snapshot_date, file_key as llama_chain, {{ explode('doc') }} as p from files
),

typed as (
    select
        snapshot_date,
        llama_chain,
        {{ unix_day("p->>'date'") }} as date_day,
        cast(p->'totalCirculatingUSD'->>'peggedUSD' as double) as stablecoins_usd
    from points
)

select *, {{ is_latest('llama_chain, date_day', 'stablecoins_usd') }} as is_latest
from typed
where date_day < snapshot_date
