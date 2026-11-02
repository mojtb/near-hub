-- The wallets Bitwise lists for its NEAR ETF (NRR), inside their staking pool, per UTC day. Each balance is read from the
-- pool contract at the first block of the next day, so it closes the day. Other delegators are kept only as a total.
-- Recent days are read again each night, so the newest snapshot of a day is the one to use.
with files as ({{ bronze_files('rpc__nrr_pool_daily') }}),

days as (
    select snapshot_date, {{ explode('doc') }} as d from files
),

wallets as (
    select snapshot_date, d, {{ explode("d->'wallets'") }} as w from days
)

select
    snapshot_date,
    cast(d->>'closes_day' as date) as date_day,
    cast(d->>'height' as bigint) as block_height,
    cast(d->>'delegators' as bigint) as delegators,
    {{ yocto_to_near("d->>'other_delegators_yocto'") }} as other_delegators_near,
    w->>'account_id' as account_id,
    {{ yocto_to_near("w->>'staked'") }} as staked_near,
    {{ yocto_to_near("w->>'unstaked'") }} as unstaked_near,
    snapshot_date = max(snapshot_date) over (partition by d->>'closes_day') as is_latest
from wallets
