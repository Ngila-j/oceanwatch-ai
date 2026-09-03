"""Phase 16 — operations & platform schema."""

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
    logger.info("=== Phase 16 ops schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_system_health (
            check_time TIMESTAMP,
            component VARCHAR,
            status VARCHAR,
            detail VARCHAR,
            latency_ms DOUBLE,
            model_version VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_report_runs (
            report_id BIGINT,
            report_type VARCHAR,
            generated_at TIMESTAMP,
            period_start DATE,
            period_end DATE,
            status VARCHAR,
            summary_text VARCHAR,
            artifact_path VARCHAR,
            model_version VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_alert_deliveries (
            delivery_id BIGINT,
            alert_ref VARCHAR,
            channel VARCHAR,
            recipient VARCHAR,
            status VARCHAR,
            attempted_at TIMESTAMP,
            detail VARCHAR,
            model_version VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_api_usage_daily (
            usage_date DATE,
            endpoint VARCHAR,
            request_count BIGINT,
            error_count BIGINT,
            model_version VARCHAR
        )
        """
    )
    logger.info("=== Phase 16 schema ready ===")


if __name__ == "__main__":
    main()