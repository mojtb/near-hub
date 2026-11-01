-- Derived from NEAR's Intents dashboard on Dune: headline tiles. NEAR uploads the data behind them.
select snapshot_date, scope, metric, value_usd, {{ dune_credit() }} as derived_from
from {{ ref('stg_dune_public__tiles') }}
