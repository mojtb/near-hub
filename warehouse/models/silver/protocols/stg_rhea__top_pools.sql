-- Point in time: Rhea pools. Most are dust, so tvl_usd is the field to filter on.
with files as ({{ bronze_files('rhea__top_pools') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as p from files
)

select
    snapshot_date,
    p->>'id' as pool_id,
    p->>'pool_kind' as pool_kind,
    p->>'token_account_ids' as token_ids_json,
    p->>'token_symbols' as token_symbols_json,
    cast(p->>'total_fee' as integer) as fee_bps_hundredths,
    cast(p->>'tvl' as double) as tvl_usd,
    {{ is_latest("p->>'id'") }} as is_latest
from rows
