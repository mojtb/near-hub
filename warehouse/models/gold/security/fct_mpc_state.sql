-- Chain Signatures contract state per day, read directly from v1.signer: at the first block of the UTC day where the
-- archival node has been asked, and otherwise by that date's nightly snapshot (read_from says which).
-- The contract's state changed shape in 2025. The first version kept one key, a participant map and a threshold at the
-- top of Running; the later one keeps them under parameters, with a list of signature domains and a keyset. Both are read.
-- A day on which the contract was not Running (it was resharing its keys, say) has no row.
with state as (
    select snapshot_date, read_from, result->'Running' as r
    from ({{ contract_view_reads() }})
    where contract = 'v1.signer' and method = 'state' and (result->'Running') is not null
)

select
    snapshot_date,
    coalesce(
        json_array_length(r->'parameters'->'participants'->'participants'),
        len(json_keys(r->'participants'->'account_to_participant_id'))
    ) as participants,
    cast(coalesce(r->'parameters'->>'threshold', r->>'threshold') as integer) as threshold,
    -- The first version had no domains: it held a single key, so one signature scheme.
    coalesce(json_array_length(r->'domains'->'domains'), case when (r->'public_key') is not null then 1 end) as signature_domains,
    cast(coalesce(r->'keyset'->>'epoch_id', r->>'epoch') as bigint) as keyset_epoch,
    read_from
from state
