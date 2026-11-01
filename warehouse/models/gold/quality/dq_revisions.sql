-- Values a source changed after first publishing them. Compares the oldest and newest snapshot holding the
-- same key. An empty table means nothing was restated, or only one snapshot exists.
{% set series = [
    ('stg_defillama__intents_volume', "'near-intents'", 'volume_usd'),
    ('stg_defillama__intents_fees', 'data_type', 'value_usd'),
    ('stg_defillama__chain_tvl', 'llama_chain', 'tvl_usd'),
    ('stg_defillama__chain_fees', "llama_chain || ':' || data_type", 'value_usd'),
    ('stg_defillama__stablecoin_chain', 'llama_chain', 'stablecoins_usd'),
    ('stg_nearblocks__txn_stats', "'txns'", 'txns'),
    ('stg_nearblocks__address_stats', "'active_accounts'", 'active_accounts'),
    ('stg_nearblocks__intents_daily', 'metric', 'daily_value'),
    ('stg_nearblocks__charts_v1', "'total_supply_near'", 'total_supply_near'),
    ('stg_revenue_page__fees_daily', "'fees_usd'", 'fees_usd'),
    ('stg_revenue_page__volume_daily', "'volume_usd'", 'volume_usd')
] %}

with compared as (
    {% for model, key_expr, value in series %}
    select
        '{{ model }}' as model,
        '{{ value }}' as value_column,
        {{ key_expr }} as series_key,
        date_day,
        min(snapshot_date) as first_snapshot,
        max(snapshot_date) as last_snapshot,
        cast(min_by({{ value }}, snapshot_date) as double) as first_value,
        cast(max_by({{ value }}, snapshot_date) as double) as last_value
    from {{ ref(model) }}
    group by all
    having count(*) > 1
    {% if not loop.last %}union all{% endif %}
    {% endfor %}
)

select
    model,
    value_column,
    series_key,
    date_day,
    first_snapshot,
    last_snapshot,
    first_value,
    last_value,
    100.0 * (last_value - first_value) / nullif(abs(first_value), 0) as change_pct
from compared
where abs(last_value - first_value) > 0.0001 * greatest(abs(first_value), abs(last_value))
