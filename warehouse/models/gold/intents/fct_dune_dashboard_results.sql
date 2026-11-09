-- Every row of every Dune widget or query read so far, as returned, so nothing waits for a typed table. Two routes land
-- here: hand readings of NEAR's public Intents dashboard (read_via 'hand'), and query results through Dune's official API
-- (read_via 'api'), which needs a DUNE_API_KEY with API access and is empty until one has run. NEAR uploads the data
-- behind the dashboard, so it is self-reported. Each row credits the dashboard or the query's creator.
select
    r.snapshot_date,
    r.reading_id,
    r.query_id,
    q.title as query_title,
    'https://dune.com/queries/' || r.query_id as query_url,
    r.selection,
    r.generated_at,
    r.is_complete,
    r.row_index,
    cast(r.row_doc as varchar) as row_json,
    'hand' as read_via,
    {{ dune_credit() }} as derived_from
from {{ ref('stg_dune_public__query_results') }} r
left join {{ ref('dune_queries') }} q using (query_id)

union all

select
    a.snapshot_date,
    a.query_id || '__api' as reading_id,
    a.query_id,
    q.title as query_title,
    'https://dune.com/queries/' || a.query_id as query_url,
    null as selection,
    a.generated_at,
    a.is_complete,
    a.row_index,
    cast(a.row_doc as varchar) as row_json,
    'api' as read_via,
    'Dune query ' || a.query_id || ', read through the official API; credit its creator: '
        || coalesce(q.evidence_url, 'https://dune.com/queries/' || a.query_id) as derived_from
from {{ ref('stg_dune__query_results') }} a
left join {{ ref('dune_queries') }} q using (query_id)
