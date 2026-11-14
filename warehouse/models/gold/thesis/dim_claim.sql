select claim_id, side, pillar, reading, claim, test, comparison, threshold, unit, why_this_threshold, source_url
from {{ ref('claims') }}
