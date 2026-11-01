-- Derived from NEAR's Intents dashboard on Dune: every row of every widget read by hand, as the widget returned
-- it, so nothing waits for a typed table. NEAR uploads the data behind the dashboard, so it is self-reported.
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
    {{ dune_credit() }} as derived_from
from {{ ref('stg_dune_public__query_results') }} r
left join {{ ref('dune_queries') }} q using (query_id)
