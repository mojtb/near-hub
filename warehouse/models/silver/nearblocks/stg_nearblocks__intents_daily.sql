-- Volume, swaps, accounts, tokens and chains arrive as separate endpoints with the same daily shape.
{% set series = {
    'nearblocks__intents_volume':   'volume_usd',
    'nearblocks__intents_swaps':    'swaps',
    'nearblocks__intents_accounts': 'accounts',
    'nearblocks__intents_tokens':   'tokens',
    'nearblocks__intents_chains':   'chains'
} %}

with typed as (
    {% for table, metric in series.items() %}
    select
        snapshot_date,
        '{{ metric }}' as metric,
        cast(left(r->>'date', 10) as date) as date_day,
        cast(r->>'daily' as double) as daily_value,
        cast(r->>'cumulative' as double) as cumulative_value
    from (
        select snapshot_date, {{ explode("doc->'data'") }} as r
        from ({{ bronze_files(table) }}) files
    ) rows
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select *, {{ is_latest('metric, date_day') }} as is_latest
from typed
where date_day < snapshot_date
