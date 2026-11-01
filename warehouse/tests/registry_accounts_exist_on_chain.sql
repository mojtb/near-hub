-- Every registry account must exist, except implicit accounts that only hold balances inside intents.near.
select account_id
from {{ ref('dim_entity') }}
where account_exists = false
  and account_id <> '7066024d3f20f94de601c003163367873cca78507eeca4df66d9be645f197f05'
