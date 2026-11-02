-- What Bitwise's page showed for its NEAR ETF (NRR) at each snapshot. The page holds only the current share count, so a
-- night without a snapshot leaves a gap in it. Several snapshots can show the same day, so the newest one is the one to use.
with files as ({{ bronze_files('nrr_fund__figures') }}),

typed as (
    select
        snapshot_date,
        cast(doc->>'as_of' as date) as date_day,
        cast(doc->>'shares_outstanding' as bigint) as shares_outstanding,
        cast(doc->>'net_assets_usd' as double) as net_assets_usd,
        cast(doc->>'near_in_trust' as double) as near_in_trust,
        cast(doc->>'near_in_trust_as_of' as date) as near_in_trust_as_of,
        cast(doc->>'gross_staking_rate' as double) as gross_staking_rate,
        cast(doc->>'net_staking_rate' as double) as net_staking_rate,
        cast(doc->>'staked_share' as double) as staked_share,
        cast(doc->>'premium_as_of' as date) as premium_as_of,
        cast(doc->>'volume_shares' as bigint) as volume_shares,
        json_array_length(doc->'wallets') as listed_wallets
    from files
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
