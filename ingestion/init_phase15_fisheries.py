"""Phase 15 — fisheries intelligence schema (Kenya EEZ)."""

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
    logger.info("=== Phase 15 fisheries schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_fishing_effort_grid (
            cell_id VARCHAR,
            effort_date DATE,
            lat DOUBLE,
            lon DOUBLE,
            hours DOUBLE,
            source VARCHAR,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_fishing_hotspots (
            hotspot_id BIGINT,
            as_of_date DATE,
            lat DOUBLE,
            lon DOUBLE,
            total_hours DOUBLE,
            cell_count INTEGER,
            intensity_score DOUBLE,
            hotspot_rank INTEGER,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_fisheries_seasonality (
            month_num INTEGER,
            month_name VARCHAR,
            total_hours DOUBLE,
            avg_daily_hours DOUBLE,
            observation_days INTEGER,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_illegal_fishing_risk (
            as_of_date DATE,
            region_id VARCHAR,
            gfw_hours DOUBLE,
            fishing_vessel_ais INTEGER,
            hotspot_intensity DOUBLE,
            anomaly_pressure DOUBLE,
            risk_score DOUBLE,
            risk_level VARCHAR,
            confidence_score DOUBLE,
            drivers VARCHAR,
            disclaimer VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_fisheries_alerts (
            alert_id BIGINT,
            as_of_date DATE,
            region_id VARCHAR,
            alert_type VARCHAR,
            severity VARCHAR,
            title VARCHAR,
            message VARCHAR,
            metric_value DOUBLE,
            status VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 15 schema ready ===")


if __name__ == "__main__":
    main()
    