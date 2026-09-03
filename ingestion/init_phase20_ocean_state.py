"""Phase 20 — ocean state engine schema."""

import logging
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri():
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def main():
    logger.info("=== Phase 20 ocean state schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    for t in (
        "fact_ocean_state",
        "fact_ecological_stress",
        "fact_fisheries_conditions",
        "fact_marine_hazards",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.fact_ocean_state (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            sst_celsius DOUBLE,
            chlorophyll_mg_m3 DOUBLE,
            tide_mean_m DOUBLE,
            ocean_state_score DOUBLE,
            ocean_state_label VARCHAR,
            ecology_risk DOUBLE,
            fisheries_condition_score DOUBLE,
            port_env_signal DOUBLE,
            drivers VARCHAR,
            confidence_score DOUBLE,
            freshness_pct DOUBLE,
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
            bloom_probability DOUBLE,
            habitat_score DOUBLE,
            climate_anomaly_score DOUBLE,
            stress_score DOUBLE,
            stress_level VARCHAR,
            drivers VARCHAR,
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
            condition_score DOUBLE,
            condition_label VARCHAR,
            sst_celsius DOUBLE,
            chlorophyll_mg_m3 DOUBLE,
            habitat_score DOUBLE,
            bloom_probability DOUBLE,
            drivers VARCHAR,
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
            hazard_type VARCHAR,
            severity VARCHAR,
            score DOUBLE,
            message VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 20 schema ready ===")


if __name__ == "__main__":
    main()