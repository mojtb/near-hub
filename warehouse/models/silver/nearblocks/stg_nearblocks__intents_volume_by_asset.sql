-- NearBlocks lists a token under the chain its contract is on, so Bitcoin bridged to NEAR arrives as near. blockchain
-- is the chain the asset is counted on, with bridged Bitcoin as btc; listed_blockchain keeps NearBlocks' own value.
with files as ({{ bronze_files('nearblocks__intents_volume_by_asset') }}),

rows as (
    select snapshot_date, {{ explode("doc->'data'") }} as r from files
),

typed as (
    select
        snapshot_date,
        cast(left(r->>'date', 10) as date) as date_day,
        case when r->>'token_id' in ({{ bridged_bitcoin_tokens() }}) then 'btc' else r->>'blockchain' end as blockchain,
        r->>'blockchain' as listed_blockchain,
        r->>'symbol' as symbol,
        r->>'token_id' as token_id,
        cast(r->>'volume' as double) as volume_token,
        cast(r->>'volume_usd' as double) as volume_usd,
        cast(r->>'swaps' as bigint) as swaps
    from rows
)

select *, {{ is_latest('date_day, token_id') }} as is_latest
from typed
where date_day < snapshot_date
