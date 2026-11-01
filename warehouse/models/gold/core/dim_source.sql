-- Every data source with its access, limits and terms, from registry/sources.csv.
select source, provides, access, limit_observed, terms_url, terms_summary, before_going_public
from {{ ref('sources') }}
