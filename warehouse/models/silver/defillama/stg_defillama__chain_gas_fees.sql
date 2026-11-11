-- Transaction fees paid to each chain itself, from the chain's own DefiLlama adapter. file_key is the chain.
-- stg_defillama__chain_fees does not hold these: its daily totals are the sum over the applications on a chain.
with files as ({{ bronze_files('defillama__chain_gas_fees') }}),

points as (
    select
        snapshot_date,
        file_key as llama_chain,
        {{ explode("doc->'totalDataChart'") }} as p
    from files
    where doc->>'protocolType' = 'chain'
),

typed as (
    select
        snapshot_date,
        llama_chain,
        {{ unix_day("p->>0") }} as date_day,
        cast(p->>1 as double) as gas_fees_usd
    from points
)

select *, {{ is_latest('llama_chain, date_day', 'gas_fees_usd') }} as is_latest
from typed
where date_day < snapshot_date
