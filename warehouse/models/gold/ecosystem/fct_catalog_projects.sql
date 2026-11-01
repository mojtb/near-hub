-- NEAR Catalog entries per read, for counting projects by tag over time. tags_json is the catalog's own map.
select snapshot_date, slug, project_name, tagline, tags_json
from {{ ref('stg_nearcatalog__projects') }}
