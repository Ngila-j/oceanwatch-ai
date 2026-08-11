
  
    

  create  table "oceanwatch_db"."public"."stg_tides__dbt_tmp"
  
  
    as
  
  (
    

select
    t::timestamp          as observation_time,
    v::float              as tide_height_meters,
    s::float              as residual,
    current_timestamp     as loaded_at
from "oceanwatch_db"."public"."raw_tides"
  );
  