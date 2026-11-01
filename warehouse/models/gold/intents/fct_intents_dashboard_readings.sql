-- Headline tiles read from NEAR's public Dune dashboard. NEAR uploads the data behind them.
select snapshot_date, scope, metric, value_usd
from {{ ref('stg_dune_public__tiles') }}
