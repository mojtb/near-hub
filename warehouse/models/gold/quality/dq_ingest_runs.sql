-- How each dataset fared on each run date: ok, partial, skipped or failed, and why.
select snapshot_date, dataset, status, detail, files, seconds
from {{ ref('stg_ingest__runs') }}
