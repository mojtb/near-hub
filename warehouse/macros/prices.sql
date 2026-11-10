{# NearBlocks' NEAR price per UTC day, as the close of that day. NearBlocks stamps a day's price at 00:00 UTC, so the value
   stamped D+1 is the close of D. /v3/price-stats is read first, and /v1/charts for days before its window; the two agree
   on every day both hold. A price of 0 means none. Used by fct_market_daily and dq_reconciliation. #}
{% macro nearblocks_daily_close() %}
    select date_day, lead(near_price_usd) over (order by date_day) as price_usd
    from (
        select date_day, coalesce(v3.near_price_usd, v1.near_price_usd) as near_price_usd
        from (select date_day, nullif(near_price_usd, 0) as near_price_usd from {{ ref('stg_nearblocks__charts_v1') }} where is_latest) v1
        full join (select date_day, nullif(near_price_usd, 0) as near_price_usd from {{ ref('stg_nearblocks__price_stats') }} where is_latest) v3
            using (date_day)
    )
{% endmacro %}
