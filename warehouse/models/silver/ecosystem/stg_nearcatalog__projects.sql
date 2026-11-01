-- Point in time: the catalog is one object keyed by project slug.
with files as ({{ bronze_files('nearcatalog__projects') }}),

slugs as (
    select snapshot_date, doc, unnest(json_keys(doc)) as slug from files
)

select
    snapshot_date,
    slug,
    doc->slug->'profile'->>'name' as project_name,
    doc->slug->'profile'->>'tagline' as tagline,
    doc->slug->'profile'->'tags' as tags_json,
    {{ is_latest('slug') }} as is_latest
from slugs
