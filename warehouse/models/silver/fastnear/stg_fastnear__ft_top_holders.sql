-- Point in time: largest holders per registry token. The API returns them sorted by balance.
with files as ({{ bronze_files('fastnear__ft_top_holders') }}),

rows as (
    select snapshot_date, doc->>'token_id' as token_id, {{ explode("doc->'accounts'") }} as a from files
)

select
    snapshot_date,
    token_id,
    a->>'account_id' as holder_account_id,
    a->>'balance' as balance_raw,
    cast(a->>'balance' as hugeint) as balance_units,
    row_number() over (partition by snapshot_date, token_id order by cast(a->>'balance' as hugeint) desc, a->>'account_id') as holder_rank,
    {{ is_latest("token_id, a->>'account_id'") }} as is_latest
from rows
