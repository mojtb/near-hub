{# Every read of a contract view, one per date, contract and method: the replay at the first block of the UTC day where
   there is one, and otherwise that date's nightly read. A contract's views on a date all come from the same read, so
   figures that must agree with each other (a liquid staking token's supply, price and staked NEAR) are from one block.
   read_from says which: archival is the day's first block, nightly is the tip when the snapshot ran, some hours later. #}
{% macro contract_view_reads() %}
    select date_day as snapshot_date, 'archival' as read_from, contract, method, result
    from {{ ref('stg_rpc__contract_views_history') }}
    where is_latest and error is null
    union all
    select n.snapshot_date, 'nightly' as read_from, n.contract, n.method, n.result
    from {{ ref('stg_rpc__contract_views') }} n
    where not exists (
        select 1 from {{ ref('stg_rpc__contract_views_history') }} h
        where h.is_latest and h.error is null and h.date_day = n.snapshot_date and h.contract = n.contract
    )
{% endmacro %}
