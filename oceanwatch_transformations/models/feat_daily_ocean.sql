{{ config(materialized="table") }}

select
    date_key,
    sst_celsius,
    chlorophyll_mg_m3,
    tide_mean_m,
    tide_min_m,
    tide_max_m,
    lag(sst_celsius, 1) over (order by date_key) as sst_lag_1,
    lag(sst_celsius, 7) over (order by date_key) as sst_lag_7,
    avg(sst_celsius) over (order by date_key rows between 6 preceding and current row) as sst_roll_7,
    current_timestamp as built_at
from {{ ref("fact_ocean_conditions") }}