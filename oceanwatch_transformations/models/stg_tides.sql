{{ config(materialized="table") }}

select
    t::timestamp          as observation_time,
    v::float              as tide_height_meters,
    s::float              as residual,
    current_timestamp     as loaded_at
from {{ source("ocean_raw", "raw_tides") }}