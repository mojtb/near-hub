select epoch_height, sum(stake_share) as total
from {{ ref('fct_validator_epoch') }}
group by epoch_height
having abs(sum(stake_share) - 1) > 0.000001
