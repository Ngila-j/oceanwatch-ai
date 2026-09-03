"""Phase 21 — unified risk engine schema."""

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
    logger.info("=== Phase 21 risk engine schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    for t in (
        "fact_unified_risk_drivers",
        "fact_unified_risk",
        "fact_unified_risk_composite",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.fact_unified_risk (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            domain VARCHAR,
            risk_score DOUBLE,
            risk_level VARCHAR,
            confidence_score DOUBLE,
            freshness_pct DOUBLE,
            data_sources_count INTEGER,
            drivers VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_unified_risk_composite (
            as_of_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            composite_score DOUBLE,
            composite_level VARCHAR,
            port_score DOUBLE,
            maritime_score DOUBLE,
            fishery_score DOUBLE,
            ecology_score DOUBLE,
            weather_score DOUBLE,
            confidence_score DOUBLE,
            freshness_pct DOUBLE,
            data_sources_count INTEGER,
            drivers VARCHAR,
            model_name VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_unified_risk_drivers (
            as_of_date DATE,
            region_id VARCHAR,
            domain VARCHAR,
            driver_name VARCHAR,
            contribution DOUBLE,
            direction VARCHAR,
            detail VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 21 schema ready ===")


if __name__ == "__main__":
    main()