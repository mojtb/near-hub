-- Every data source with its access, limits and terms, from registry/sources.csv.
select source, provides, access, limit_observed, terms_url, terms_summary, publication_note
from {{ ref('sources') }}
