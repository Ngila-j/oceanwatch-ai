{{ config(materialized="table") }}

with date_spine as (
    select
        generate_series(
            '2026-01-01'::date,
            '2026-12-31'::date,
            '1 day'::interval
        )::date as date_day
)

select
    date_day                                          as date_key,
    date_day,
    extract(year from date_day)::int                  as year,
    extract(month from date_day)::int                 as month,
    extract(day from date_day)::int                   as day,
    to_char(date_day, 'Month')                        as month_name,
    extract(dow from date_day)::int                   as day_of_week,
    to_char(date_day, 'Day')                          as day_name,
    case when extract(dow from date_day) in (0, 6) then true else false end as is_weekend
from date_spine