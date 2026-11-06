-- What each token's contract says about itself through ft_metadata. A token is read once, so its row sits in the snapshot
-- it was read in, and is_latest marks the answer to use. error_name says why a token has no decimals. Name and symbol are
-- the contract's own claim: a token calling itself USDC need not be USDC.
with files as ({{ bronze_files('rpc__ft_metadata') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as r from files
)

select
    snapshot_date,
    r->>'token_id' as token_id,
    r->>'spec' as spec,
    r->>'name' as name,
    r->>'symbol' as symbol,
    cast(r->>'decimals' as integer) as decimals,
    r->>'error' as error_name,
    cast(r->>'block_height' as bigint) as block_height,
    {{ is_latest("r->>'token_id'", "cast(r->>'block_height' as bigint)") }} as is_latest
from rows
