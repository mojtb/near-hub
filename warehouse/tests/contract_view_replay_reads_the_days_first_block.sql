-- A replayed day must have been read at the block rpc/block_day holds for that day, or its figures belong to another day.
select h.date_day, h.block_height as replayed_at, b.block_height as days_first_block
from (select distinct date_day, block_height from {{ ref('stg_rpc__contract_views_history') }} where is_latest) h
left join {{ ref('stg_rpc__block_day') }} b on b.date_day = h.date_day and b.is_latest
where b.block_height is null or b.block_height <> h.block_height
