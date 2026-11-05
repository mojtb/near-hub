-- End-of-day balances of lockup.near and contributors.near, the two accounts NEAR Explorer subtracted along with the lockups,
-- from FastNear's running balance on each day with a native transfer. read_with marks the one view_account read per snapshot.
with files as ({{ bronze_files('rpc__lockups') }}),

rows as (
    select snapshot_date, {{ explode('doc') }} as r from files where file_key = 'foundation_balances'
)

select
    snapshot_date,
    r->>'account_id' as account_id,
    cast(r->>'date_day' as date) as date_day,
    {{ yocto_to_near("r->>'balance_yocto'") }} as balance_near,
    coalesce(r->>'read_with', 'transfers') as read_with,
    {{ is_latest("r->>'account_id', r->>'date_day', coalesce(r->>'read_with', 'transfers')") }} as is_latest
from rows
