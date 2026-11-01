-- Tracked governance threads, one row per thread per snapshot.
with files as ({{ bronze_files('gov__topics') }})

select
    snapshot_date,
    cast(doc->>'id' as bigint) as topic_id,
    doc->>'title' as title,
    cast(left(doc->>'created_at', 10) as date) as created_date,
    cast(left(doc->>'last_posted_at', 10) as date) as last_post_date,
    cast(doc->>'posts_count' as bigint) as posts,
    cast(doc->>'views' as bigint) as views,
    cast(doc->>'like_count' as bigint) as likes,
    cast(doc->>'closed' as boolean) as is_closed,
    {{ is_latest("doc->>'id'") }} as is_latest
from files
