-- Activity per receiver, counted from evenly spaced sample blocks. These are estimates; see blocks_sampled.
with files as ({{ bronze_files('neardata__receiver_sample') }}),

rows as (
    select
        snapshot_date,
        cast(doc->>'day' as date) as date_day,
        cast(doc->>'blocks_sampled' as integer) as blocks_sampled,
        cast(doc->>'blocks_in_day' as bigint) as blocks_in_day,
        cast(doc->>'txns_sampled' as bigint) as txns_sampled,
        cast(doc->>'receipts_sampled' as bigint) as receipts_sampled,
        {{ explode("doc->'receivers'") }} as r
    from files
)

select
    snapshot_date,
    date_day,
    blocks_sampled,
    blocks_in_day,
    txns_sampled,
    receipts_sampled,
    r->>'account_id' as account_id,
    cast(r->>'txns' as bigint) as txns,
    cast(r->>'receipts' as bigint) as receipts,
    cast(r->>'distinct_signers' as bigint) as distinct_signers,
    cast(r->>'gas_burnt' as hugeint) as gas_burnt,
    {{ yocto_to_near("r->>'tokens_burnt_yocto'") }} as tokens_burnt_near
from rows
qualify row_number() over (partition by date_day, r->>'account_id' order by snapshot_date desc) = 1
