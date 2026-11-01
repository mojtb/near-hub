-- Derived from NEAR's Intents dashboard on Dune: all-time gross fees per referral channel on the snapshot date.
select
    snapshot_date,
    referral,
    fees_usd,
    fees_usd / sum(fees_usd) over (partition by snapshot_date) as share_of_listed_fees,
    row_number() over (partition by snapshot_date order by fees_usd desc, referral) as channel_rank,
    {{ dune_credit() }} as derived_from
from {{ ref('stg_dune_public__fee_channels') }}
