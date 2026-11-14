-- What intents.near held of named tokens at past blocks, read from the token contracts through the archival node: one
-- row per day closed and token asked. A balance is read at the first block of the next UTC day, so it closes date_day.
-- chosen_as says why a token was read: wrapped_near, dollar_token (the 1Click list priced it within 2% of one dollar on
-- the day of the read) or other_asset (the list names it with the symbol of an asset holding at least 1% of the pool on
-- the newest day of NEAR's dashboard series). `error` is the chain's own reason a token has no balance: UNKNOWN_ACCOUNT
-- or NO_CONTRACT_CODE where the contract did not exist yet, CONTRACT_EXECUTION_ERROR where the call ran and failed.
-- symbol is without 1Click's (DEPRECATED) mark, as in stg_oneclick__tokens; listed_symbol keeps the list's own spelling.
-- A token is asked about once for a day; a token that joins the list later is read on a later snapshot, in a file of
-- its own. If a token is ever read twice for a day, the newest read is the one to use.
with files as ({{ bronze_files('rpc__intents_pool_history') }}),

balances as (
    select
        snapshot_date,
        cast(doc->>'closes_day' as date) as date_day,
        cast(doc->>'block_height' as bigint) as block_height,
        {{ explode("doc->'balances'") }} as b
    from files
)

select
    snapshot_date,
    date_day,
    block_height,
    b->>'asset_id' as asset_id,
    b->>'standard' as token_standard,
    b->>'contract' as contract_id,
    b->>'chosen_as' as chosen_as,
    regexp_replace(b->>'listed_symbol', '_?\(deprecated\)$', '', 'i') as symbol,
    b->>'listed_symbol' as listed_symbol,
    cast(b->>'decimals' as integer) as decimals,
    b->>'balance' as balance_raw,
    try_cast(b->>'balance' as double) / pow(10, cast(b->>'decimals' as integer)) as amount_token,
    b->>'error' as error,
    {{ is_latest("date_day, b->>'asset_id'") }} as is_latest
from balances
