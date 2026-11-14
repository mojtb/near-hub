-- A reading of the Intents pool must have been taken at the block rpc/block_day holds for the next day, the first block
-- after the day it closes, or its balances belong to another day.
select h.date_day, h.block_height as read_at, b.block_height as next_days_first_block
from (select distinct date_day, block_height from {{ ref('stg_rpc__intents_pool_history') }} where is_latest) h
left join {{ ref('stg_rpc__block_day') }} b on b.date_day = h.date_day + 1 and b.is_latest
where b.block_height is null or b.block_height <> h.block_height
