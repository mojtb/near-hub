-- House of Stake proposals as the voting contract reports them, one row per proposal per snapshot.
with files as ({{ bronze_files('rpc__hos_proposals') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as p from files
)

select
    snapshot_date,
    cast(p->>'id' as integer) as proposal_id,
    p->>'title' as title,
    p->>'status' as status,
    p->>'flow' as flow,
    p->>'proposer_id' as proposer_id,
    p->>'link' as link,
    {{ unix_day("cast(p->>'creation_time_ns' as hugeint) // 1000000000") }} as created_date,
    {{ unix_day("cast(p->>'voting_start_time_ns' as hugeint) // 1000000000") }} as voting_start_date,
    {{ unix_day("(cast(p->>'voting_start_time_ns' as hugeint) + cast(p->>'voting_duration_ns' as hugeint)) // 1000000000") }} as voting_end_date,
    {{ yocto_to_near("p->'votes'->0->>'total_venear'") }} as option_0_venear,
    {{ yocto_to_near("p->'votes'->1->>'total_venear'") }} as option_1_venear,
    {{ yocto_to_near("p->'votes'->2->>'total_venear'") }} as option_2_venear,
    cast(p->'total_votes'->>'total_votes' as integer) as voters,
    {{ yocto_to_near("p->'total_votes'->>'total_venear'") }} as votes_venear,
    {{ yocto_to_near("p->'snapshot_and_state'->>'total_venear'") }} as eligible_venear,
    cast(p->>'quorum_threshold_bps' as integer) / 10000.0 as quorum_threshold,
    cast(p->>'approval_threshold_bps' as integer) / 10000.0 as approval_threshold,
    cast(p->'votes'->0->>'total_votes' as integer) as option_0_voters,
    cast(p->'votes'->1->>'total_votes' as integer) as option_1_voters,
    cast(p->'votes'->2->>'total_votes' as integer) as option_2_voters,
    cast(p->'snapshot_and_state'->'snapshot'->>'length' as integer) as snapshot_accounts,
    p->>'reviewer_id' as reviewer_id,
    p->>'actions' is not null as has_actions,
    -- The moment voting closes, and the moment the timelock after it ends: the same when the proposal has no timelock
    make_timestamp(cast((cast(p->>'voting_start_time_ns' as hugeint) + cast(p->>'voting_duration_ns' as hugeint)) // 1000 as bigint)) as voting_end_utc,
    make_timestamp(cast((cast(p->>'voting_start_time_ns' as hugeint) + cast(p->>'voting_duration_ns' as hugeint)
                         + cast(p->>'timelock_duration_ns' as hugeint)) // 1000 as bigint)) as timelock_end_utc,
    -- The contract stores how fast veNEAR grows as a fraction for each nanosecond; times the nanoseconds in 365 days
    cast(p->'snapshot_and_state'->'venear_growth_config'->'FixedRate'->'annual_growth_rate_ns'->>'numerator' as double)
        / cast(p->'snapshot_and_state'->'venear_growth_config'->'FixedRate'->'annual_growth_rate_ns'->>'denominator' as double)
        * 365 * 86400 * 1e9 as venear_growth_per_year,
    {{ is_latest("p->>'id'") }} as is_latest
from rows
