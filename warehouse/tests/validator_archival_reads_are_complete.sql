-- Silver lets an archival read of an epoch win over the nightly mid-epoch read, on the promise that an archival read is
-- of a finished epoch and carries final counts. The backfill keeps that promise by saving nothing from an epoch still in
-- progress. If one slipped through, its partial counts would pass for final ones for good, so no archival row may belong
-- to an incomplete epoch.
select epoch_height, read_from, sum(blocks_expected) as blocks_counted
from {{ ref('fct_validator_epoch') }}
where read_from = 'archival' and not is_epoch_complete
group by epoch_height, read_from
