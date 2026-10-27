"""Phase 20 — ocean state engine schema."""

import logging

import duckdb

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    uri = get_db_uri()
    logger.info("=== Phase 20 ocean state schema → %s ===", uri.split("@")[-1])
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{uri}' AS pg (TYPE POSTGRES)")

    for t in (
        "fact_marine_hazards",
        "fact_fisheries_conditions",
        "fact_ecological_stress",
        "fact_ocean_state",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.fact_ocean_state (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            ocean_state_score DOUBLE,
            ocean_state_label VARCHAR,
            sst_c DOUBLE,
            chl_mg_m3 DOUBLE,
            tide_m DOUBLE,
            ecology_risk DOUBLE,
            fisheries_condition_score DOUBLE,
            bloom_risk_score DOUBLE,
            habitat_score DOUBLE,
            climate_stress DOUBLE,
            confidence_score DOUBLE,
            freshness_pct DOUBLE,
            data_sources_count INTEGER,
            summary VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_ecological_stress (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            stress_score DOUBLE,
            stress_level VARCHAR,
            drivers VARCHAR,
            sst_contrib DOUBLE,
            chl_contrib DOUBLE,
            bloom_contrib DOUBLE,
            climate_contrib DOUBLE,
            confidence_score DOUBLE,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_fisheries_conditions (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            condition_score DOUBLE,
            condition_label VARCHAR,
            habitat_score DOUBLE,
            thermal_fit DOUBLE,
            productivity_proxy DOUBLE,
            pressure_penalty DOUBLE,
            confidence_score DOUBLE,
            notes VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_marine_hazards (
            hazard_id BIGINT,
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            hazard_type VARCHAR,
            severity VARCHAR,
            score DOUBLE,
            lat DOUBLE,
            lon DOUBLE,
            narrative VARCHAR,
            source_table VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.close()
    logger.info("=== Phase 20 schema ready ===")


if __name__ == "__main__":
    main()
