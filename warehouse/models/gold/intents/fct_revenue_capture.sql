-- Capture rate per mechanism and window as NEAR publishes it on revenue.near.org. One row per reading.
select snapshot_date, mechanism, time_window, capture_rate
from {{ ref('stg_revenue_page__capture_rates') }}
