-- Headline tiles of NEAR's public Intents dashboard on Dune, per reading: all-time, 30-day, 7-day and past-day volume,
-- total generated fees and TVL, each for all, public and confidential Intents. NEAR uploads the data behind them.
-- The reading of 2026-11-01 lists the tiles as the page displayed them, rounded to whole dollars. Later readings keep
-- each widget's response, so a tile is read from the query behind it, unrounded; a tile over a daily series shows the
-- latest day. A tile whose response was not kept has no row for that reading.
with files as ({{ bronze_files('dune_public__near_intents_dashboard') }}),

page_rows as (
    select snapshot_date, {{ explode("doc->'tiles'") }} as t from files
),

from_page as (
    select
        snapshot_date,
        t->>'scope' as scope,
        t->>'metric' as metric,
        cast(t->>'value_usd' as double) as value_usd
    from page_rows
),

-- The query and column behind each tile, matched on 2026-11-10 to the values the dashboard displayed.
tile_columns (query_id, column_name, scope, metric) as (
    values
        (5179085, 'cumulative_volume_usd', 'all', 'volume_all_time'),
        (5179085, 'cumulative_public_volume_usd', 'public', 'volume_all_time'),
        (5179085, 'cumulative_confidential_volume_usd', 'confidential', 'volume_all_time'),
        (5175176, 'volume', 'all', 'volume_30d'),
        (5175176, 'public_volume', 'public', 'volume_30d'),
        (5175176, 'confidential_volume', 'confidential', 'volume_30d'),
        (5175173, 'volume', 'all', 'volume_7d'),
        (5175173, 'public_volume', 'public', 'volume_7d'),
        (5175173, 'confidential_volume', 'confidential', 'volume_7d'),
        (5175161, 'volume', 'all', 'volume_past_day'),
        (5175161, 'public_volume', 'public', 'volume_past_day'),
        (5175161, 'confidential_volume', 'confidential', 'volume_past_day'),
        (6162606, 'fees', 'all', 'total_generated_fees'),
        (6162606, 'public_fees', 'public', 'total_generated_fees'),
        (6162606, 'confidential_fees', 'confidential', 'total_generated_fees'),
        (7586891, 'tvl_usd', 'all', 'tvl'),
        (7586891, 'public_tvl_usd', 'public', 'tvl'),
        (7586891, 'confidential_tvl_usd', 'confidential', 'tvl')
),

values_read as (
    select
        r.snapshot_date,
        c.scope,
        c.metric,
        cast(r.row_doc->>c.column_name as double) as value_usd,
        coalesce(r.row_doc->>'date_at', '') as date_at
    from {{ ref('stg_dune_public__query_results') }} r
    join tile_columns c on c.query_id = r.query_id
    where r.row_doc->>c.column_name is not null
),

from_widgets as (
    select snapshot_date, scope, metric, arg_max(value_usd, date_at) as value_usd
    from values_read
    group by snapshot_date, scope, metric
)

select * from from_page
union all
select * from from_widgets
where snapshot_date not in (select snapshot_date from from_page)
