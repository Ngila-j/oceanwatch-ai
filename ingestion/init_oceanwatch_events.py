"""Create oceanwatch_events + risk_scores (Phase 11 core)."""

import logging
from datetime import datetime

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def main():
    logger.info("=== Init oceanwatch_events / risk_scores ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.oceanwatch_events (
            event_id BIGINT,
            event_type VARCHAR,
            event_category VARCHAR,
            severity VARCHAR,
            event_time TIMESTAMP,
            latitude DOUBLE,
            longitude DOUBLE,
            region_id VARCHAR,
            entity_id VARCHAR,
            confidence_score DOUBLE,
            risk_score DOUBLE,
            model_version VARCHAR,
            source VARCHAR,
            title VARCHAR,
            description VARCHAR,
            evidence VARCHAR,
            status VARCHAR,
            created_at TIMESTAMP
        )
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.risk_scores (
            risk_id BIGINT,
            domain VARCHAR,
            entity_id VARCHAR,
            region_id VARCHAR,
            risk_score DOUBLE,
            confidence_score DOUBLE,
            risk_level VARCHAR,
            reason VARCHAR,
            data_freshness_minutes DOUBLE,
            model_version VARCHAR,
            as_of_time TIMESTAMP,
            created_at TIMESTAMP
        )
        """
    )

    logger.info("=== Schema ready ===")


if __name__ == "__main__":
    main()