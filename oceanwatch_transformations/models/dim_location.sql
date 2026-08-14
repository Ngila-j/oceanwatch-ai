{{ config(materialized="table") }}

select
    1                                           as location_key,
    'Western Indian Ocean'                      as region_name,
    'Kenya EEZ / Mombasa area'                  as description,
    39.0                                        as min_longitude,
    45.0                                        as max_longitude,
    -5.0                                        as min_latitude,
    2.0                                         as max_latitude,
    (39.0 + 45.0) / 2                           as centroid_lon,
    (-5.0 + 2.0) / 2                            as centroid_lat,

    -- PostGIS geometry: bounding box polygon
    ST_SetSRID(
        ST_MakeEnvelope(39.0, -5.0, 45.0, 2.0),
        4326
    )                                           as geom,

    -- Centroid point
    ST_SetSRID(
        ST_MakePoint((39.0 + 45.0) / 2, (-5.0 + 2.0) / 2),
        4326
    )                                           as centroid_geom