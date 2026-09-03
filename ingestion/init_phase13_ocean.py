"""Phase 13 — ocean intelligence schema (Kenya EEZ)."""

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
    logger.info("=== Phase 13 ocean schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_ocean_climate_anomalies (
            as_of_date DATE,
            region_id VARCHAR,
            metric VARCHAR,
            current_value DOUBLE,
            mean_7d DOUBLE,
            mean_30d DOUBLE,
            anomaly_value DOUBLE,
            anomaly_pct DOUBLE,
            severity VARCHAR,
            confidence_score DOUBLE,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_ocean_risk_fusion (
            as_of_date DATE,
            region_id VARCHAR,
            sst_celsius DOUBLE,
            chlorophyll_mg_m3 DOUBLE,
            bloom_probability DOUBLE,
            habitat_score DOUBLE,
            climate_risk_score DOUBLE,
            bloom_risk_score DOUBLE,
            habitat_stress_score DOUBLE,
            composite_ocean_risk DOUBLE,
            risk_level VARCHAR,
            confidence_score DOUBLE,
            early_warning_flag BOOLEAN,
            early_warning_message VARCHAR,
            drivers VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_environmental_warnings (
            warning_id BIGINT,
            as_of_date DATE,
            region_id VARCHAR,
            warning_type VARCHAR,
            severity VARCHAR,
            title VARCHAR,
            message VARCHAR,
            metric_value DOUBLE,
            confidence_score DOUBLE,
            status VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 13 schema ready ===")


if __name__ == "__main__":
    main()