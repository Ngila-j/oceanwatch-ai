"""Phase 22 — event bus schema."""

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
    logger.info("=== Phase 22 event bus schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    for t in ("event_bus", "event_bus_topics", "event_bus_consumers"):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.event_bus_topics (
            topic VARCHAR PRIMARY KEY,
            description VARCHAR,
            status VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.event_bus (
            event_id BIGINT,
            topic VARCHAR,
            event_type VARCHAR,
            severity VARCHAR,
            payload VARCHAR,
            region_id VARCHAR,
            country_id VARCHAR,
            source_table VARCHAR,
            status VARCHAR,
            created_at TIMESTAMP,
            processed_at TIMESTAMP,
            model_version VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.event_bus_consumers (
            consumer_id VARCHAR PRIMARY KEY,
            consumer_name VARCHAR,
            topics VARCHAR,
            status VARCHAR,
            last_seen_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 22 schema ready ===")


if __name__ == "__main__":
    main()