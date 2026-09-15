"""Phase 24 — intelligence report engine schema."""

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
    logger.info("=== Phase 24 reports schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    for t in (
        "dim_report_types",
        "fact_report_runs",
        "fact_report_sections",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.dim_report_types (
            report_type_id VARCHAR PRIMARY KEY,
            report_name VARCHAR,
            cadence VARCHAR,
            audience VARCHAR,
            status VARCHAR,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_report_runs (
            run_id BIGINT,
            report_type_id VARCHAR,
            report_date DATE,
            region_id VARCHAR,
            country_id VARCHAR,
            title VARCHAR,
            summary VARCHAR,
            overall_status VARCHAR,
            confidence_score DOUBLE,
            section_count INTEGER,
            model_version VARCHAR,
            generated_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_report_sections (
            section_id BIGINT,
            run_id BIGINT,
            section_order INTEGER,
            section_code VARCHAR,
            section_title VARCHAR,
            status VARCHAR,
            metric_value DOUBLE,
            metric_label VARCHAR,
            narrative VARCHAR,
            evidence VARCHAR,
            model_version VARCHAR
        )
        """
    )
    logger.info("=== Phase 24 schema ready ===")


if __name__ == "__main__":
    main()