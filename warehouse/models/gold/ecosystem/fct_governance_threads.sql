-- Engagement on the tracked governance threads, per read. Governance outcomes belong in dim_event.
select snapshot_date, topic_id, title, created_date, last_post_date, posts, views, likes, is_closed
from {{ ref('stg_gov__topics') }}
