-- Where the data came from, per dataset and snapshot: files, size, the URL read, when, and any change made
-- before saving. Cite this next to a chart so a reader can find the exact responses behind it.
select
    source,
    dataset,
    snapshot_date,
    count(*) as files,
    sum(bytes) as bytes,
    sum(rows) as declared_rows,
    min(url) as example_url,
    min(fetched_at) as first_fetched_at,
    max(fetched_at) as last_fetched_at,
    max(note) as note
from {{ ref('stg_ingest__manifest') }}
group by source, dataset, snapshot_date
