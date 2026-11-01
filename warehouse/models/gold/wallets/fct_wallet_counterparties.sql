-- Who each crawled wallet deals with. Counterparties outside the registry stay unlabelled until there is
-- evidence of who they are, so an empty entity means unknown, not unimportant.
select
    account_id,
    counterparty_id,
    any_value(counterparty_entity) as counterparty_entity,
    any_value(counterparty_category) as counterparty_category,
    count(*) as transfers,
    coalesce(sum(amount_usd) filter (where direction = 'in'), 0) as usd_in,
    coalesce(-sum(amount_usd) filter (where direction = 'out'), 0) as usd_out,
    min(date_day) as first_seen,
    max(date_day) as last_seen
from {{ ref('fct_wallet_transfers') }}
group by account_id, counterparty_id
