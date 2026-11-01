-- 1Click swaps only, from the Intents Explorer API. Empty until INTENTS_EXPLORER_JWT is set.
with files as ({{ bronze_files('intents_explorer__transactions') }}),

rows as (
    select snapshot_date, {{ explode("coalesce(doc->'data', doc)") }} as t from files
),

typed as (
    select
        snapshot_date,
        t->>'depositAddress' as deposit_address,
        t->>'depositMemo' as deposit_memo,
        t->>'originAsset' as origin_asset,
        t->>'destinationAsset' as destination_asset,
        t->>'status' as status,
        t->>'referral' as referral,
        cast(t->>'amountInUsd' as double) as amount_in_usd,
        cast(t->>'amountOutUsd' as double) as amount_out_usd,
        cast(t->>'createdAtTimestamp' as bigint) as created_at_unix,
        {{ unix_day("t->>'createdAtTimestamp'") }} as date_day
    from rows
)

select *
from typed
qualify row_number() over (partition by deposit_address, deposit_memo, created_at_unix order by snapshot_date desc) = 1
