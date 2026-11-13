-- Derived from NEAR's Intents dashboard on Dune: all Intents volume per blockchain per day, public and confidential
-- together, with both dashboard filters on ALL (query 5157565, the full history, first read on 2026-11-10). Each
-- dollar of a swap is counted once, and the dashboard does not say on which side of the swap. The blockchain code is
-- the dashboard's in lower case, which is how NearBlocks and the Explorer write the same chains. A later reading
-- replaces an earlier one's value for the same day. fct_intents_chain_daily is the public-only view from NearBlocks.
with widget as (
    select
        snapshot_date,
        generated_at,
        reading_id,
        cast(row_doc->>'date_at' as date) as date_day,
        lower(row_doc->>'blockchain') as blockchain,
        cast(row_doc->>'volume_usd' as double) as volume_usd
    from {{ ref('stg_dune_public__query_results') }}
    where query_id = 5157565 and selection = 'blockchain-ALL__symbol-ALL' and is_complete
),

latest as (
    select
        *,
        row_number() over (
            partition by date_day, blockchain order by snapshot_date desc, generated_at desc nulls last, reading_id
        ) = 1 as keep
    from widget
)

select
    date_day,
    blockchain,
    volume_usd,
    volume_usd / nullif(sum(volume_usd) over (partition by date_day), 0) as share_of_day,
    snapshot_date,
    {{ dune_credit() }} as derived_from
from latest
where keep
