-- House of Stake proposals read directly from vote.dao, as of the newest snapshot. A status of Voting means
-- the numbers are still moving. Proposals made to try the contract out, and jokes, are kept and marked with is_test.
-- Every real proposal so far links to its forum thread on gov.near.org or has no link; every test or joke links
-- somewhere else or says test in its title.
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
    snapshot_date as read_on,
    regexp_matches(lower(title), '\btes+t\b')
        or (link is not null and link not like 'https://gov.near.org/t/%') as is_test
from {{ ref('stg_rpc__hos_proposals') }}
where is_latest
