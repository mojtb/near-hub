-- Chain Signatures activity per day, from NearBlocks' signer statistics.
select date_day, txns, signers, gas_burnt
from {{ ref('stg_nearblocks__signer_stats') }}
where is_latest
