-- House of Stake proposals read directly from vote.dao, as of the newest snapshot. A status of Voting means
-- the numbers are still moving. Test and spam proposals are kept and can be filtered on status or title.
select
    proposal_id,
    title,
    status,
    flow,
    proposer_id,
    link,
    created_date,
    voting_start_date,
    voting_end_date,
    option_0_venear as for_venear,
    option_1_venear as against_venear,
    option_2_venear as abstain_venear,
    voters,
    votes_venear,
    eligible_venear,
    votes_venear / nullif(eligible_venear, 0) as turnout,
    quorum_threshold,
    approval_threshold,
    snapshot_date as read_on
from {{ ref('stg_rpc__hos_proposals') }}
where is_latest
