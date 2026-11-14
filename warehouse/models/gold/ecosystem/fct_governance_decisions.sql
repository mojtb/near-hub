-- Every real vote on vote.dao, one row each, with what it decides. The vote columns are the contract's. What kind
-- of decision it is, what it changes, what it commits and whether it is in force on the chain are read by hand from
-- each proposal's own text and kept in registry/governance_decisions.csv, with the passage each rests on. A vote the
-- registry has not read yet keeps its row here with those columns empty. snapshot_accounts is every account in the
-- snapshot of venear.dao the vote was taken on, so it includes accounts that held nothing by then.
select
    p.proposal_id,
    d.hsp,
    d.short_name,
    d.kind,
    d.what_it_changes,
    p.title,
    p.status,
    p.voting_start_date,
    p.voting_end_date,
    p.voters,
    p.voters_for,
    p.voters_against,
    p.voters_abstain,
    p.snapshot_accounts,
    p.voters * 1.0 / nullif(p.snapshot_accounts, 0) as share_of_accounts_voting,
    p.for_venear / nullif(p.for_venear + p.against_venear, 0) as support,
    p.approval_threshold,
    p.for_venear,
    p.against_venear,
    p.abstain_venear,
    p.eligible_venear,
    p.turnout,
    p.quorum_threshold,
    p.timelock_end_utc,
    d.near_committed,
    d.usd_committed,
    d.ramp_months,
    d.grace_days,
    d.in_force_date,
    d.in_force_protocol_version,
    d.evidence,
    d.source_url
from {{ ref('fct_governance_proposals') }} p
left join {{ ref('governance_decisions') }} d using (proposal_id)
where p.voters > 0 and not p.is_test
