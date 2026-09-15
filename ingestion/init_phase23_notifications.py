"""Phase 23 — notification / delivery engine schema."""

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
    logger.info("=== Phase 23 notifications schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    for t in (
        "dim_notification_channels",
        "dim_notification_templates",
        "fact_notification_queue",
        "fact_notification_deliveries",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.dim_notification_channels (
            channel_id VARCHAR PRIMARY KEY,
            channel_name VARCHAR,
            channel_type VARCHAR,
            status VARCHAR,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.dim_notification_templates (
            template_id VARCHAR PRIMARY KEY,
            topic VARCHAR,
            severity_min VARCHAR,
            subject_template VARCHAR,
            body_template VARCHAR,
            status VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_notification_queue (
            queue_id BIGINT,
            event_id BIGINT,
            topic VARCHAR,
            event_type VARCHAR,
            severity VARCHAR,
            channel_id VARCHAR,
            recipient VARCHAR,
            subject VARCHAR,
            body VARCHAR,
            status VARCHAR,
            created_at TIMESTAMP,
            model_version VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_notification_deliveries (
            delivery_id BIGINT,
            queue_id BIGINT,
            event_id BIGINT,
            channel_id VARCHAR,
            recipient VARCHAR,
            delivery_status VARCHAR,
            attempt INTEGER,
            response_code VARCHAR,
            response_message VARCHAR,
            delivered_at TIMESTAMP,
            model_version VARCHAR
        )
        """
    )
    logger.info("=== Phase 23 schema ready ===")


if __name__ == "__main__":
    main()