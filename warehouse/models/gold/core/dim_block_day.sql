-- One block per UTC day, read from the archival node: monthly from 2020-08, daily from 2025-01.
select
    date_day,
    block_height,
    block_hash,
    block_timestamp_ns,
    total_supply_near,
    gas_price_yocto,
    epoch_id,
    protocol_version
from {{ ref('stg_rpc__block_day') }}
where is_latest
