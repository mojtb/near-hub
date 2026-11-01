-- Daily Chain Signatures activity on the v1.signer contract: transactions, distinct signers, gas burnt.
with files as ({{ bronze_files('nearblocks__signer_stats') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'txns' as bigint) as txns,
        cast(r->>'signers' as bigint) as signers,
        cast(r->>'gas_burnt' as hugeint) as gas_burnt
    from rows
)

select *, {{ is_latest('date_day') }} as is_latest
from typed
where date_day < snapshot_date
