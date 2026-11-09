-- fct_governance_proposals.is_test marks proposals made to try the contract out, and jokes, by a rule: the title says
-- test, or the link is not a forum thread on gov.near.org. A rule can be wrong about a proposal nobody has seen yet, for
-- instance a real one that links to a document elsewhere. A test or a joke does not pass a vote, so a flagged proposal
-- that is being voted on, has passed or is waiting out its timelock means the rule has caught a real one and needs a look.
select proposal_id, title, status, link
from {{ ref('fct_governance_proposals') }}
where is_test and status not in ('Created', 'Rejected', 'Defeated')
