{{ config(materialized="table") }}

with sst as (
    select
        time::date                      as date_key,
        thetao_mean                     as sst_celsius,
        source_file                     as sst_source_file
    from {{ source("ocean_raw", "raw_sst_daily") }}
),

chl as (
    select
        time::date                      as date_key,
        "CHL_mean"                      as chlorophyll_mg_m3,
        source_file                     as chl_source_file
    from {{ source("ocean_raw", "raw_chl_daily") }}
),

tides as (
    select
        observation_time::date          as date_key,
        avg(tide_height_meters)         as tide_mean_m,
        min(tide_height_meters)         as tide_min_m,
        max(tide_height_meters)         as tide_max_m,
        count(*)                        as tide_obs_count
    from {{ ref("stg_tides") }}
    group by 1
)

select
    coalesce(s.date_key, c.date_key, t.date_key) as date_key,
    1                                            as location_key,
    s.sst_celsius,
    c.chlorophyll_mg_m3,
    t.tide_mean_m,
    t.tide_min_m,
    t.tide_max_m,
    t.tide_obs_count,
    s.sst_source_file,
    c.chl_source_file,
    current_timestamp                            as loaded_at
from sst s
full outer join chl c  on s.date_key = c.date_key
full outer join tides t on coalesce(s.date_key, c.date_key) = t.date_key