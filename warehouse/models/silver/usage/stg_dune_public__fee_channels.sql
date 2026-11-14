-- All-time gross fees per referral channel, from the dashboard's table "Total generated fees by channel" (query
-- 6162721), which lists the top 100 channels. The reading of 2026-11-01 lists them as the page displayed them. Later
-- readings keep the table's own response, page by page, and count only when every page was read.
with files as ({{ bronze_files('dune_public__near_intents_dashboard') }}),

page_rows as (
    select snapshot_date, {{ explode("doc->'fee_channels'") }} as c from files
),

from_page as (
    select
        snapshot_date,
        c->>'referral' as referral,
        cast(c->>'fees_usd' as double) as fees_usd
    from page_rows
),

from_table as (
    select
        snapshot_date,
        row_doc->>'referral' as referral,
        cast(row_doc->>'fees' as double) as fees_usd
    from {{ ref('stg_dune_public__query_results') }}
    where query_id = 6162721 and is_complete
)

select * from from_page
union all
select * from from_table
where snapshot_date not in (select snapshot_date from from_page)
