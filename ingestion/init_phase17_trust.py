"""Phase 17 — Data Trust schema (recreate clean catalog tables)."""

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
    logger.info("=== Phase 17 trust schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    # Drop legacy conflicting shapes from earlier phases
    for t in (
        "fact_data_lineage",
        "fact_data_quality",
        "fact_data_ingestion_runs",
        "dim_data_products",
        "dim_data_sources",
        "dim_data_licenses",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.dim_data_licenses (
            license_code VARCHAR PRIMARY KEY,
            license_name VARCHAR,
            redistribution VARCHAR,
            commercial_use VARCHAR,
            attribution_required BOOLEAN,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.dim_data_sources (
            source_id VARCHAR PRIMARY KEY,
            provider VARCHAR,
            dataset_name VARCHAR,
            description VARCHAR,
            geo_coverage VARCHAR,
            temporal_coverage VARCHAR,
            update_frequency VARCHAR,
            resolution VARCHAR,
            license_code VARCHAR,
            access_type VARCHAR,
            pipeline VARCHAR,
            status VARCHAR,
            last_success_at TIMESTAMP,
            last_failure_at TIMESTAMP,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.dim_data_products (
            product_id VARCHAR PRIMARY KEY,
            source_id VARCHAR,
            product_name VARCHAR,
            description VARCHAR,
            unit VARCHAR,
            methodology VARCHAR,
            status VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_data_ingestion_runs (
            run_id BIGINT,
            source_id VARCHAR,
            product_id VARCHAR,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            rows_processed BIGINT,
            files_processed INTEGER,
            quality_score DOUBLE,
            status VARCHAR,
            error_message VARCHAR,
            model_version VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_data_quality (
            as_of_date DATE,
            source_id VARCHAR,
            product_id VARCHAR,
            completeness DOUBLE,
            freshness_hours DOUBLE,
            validity_score DOUBLE,
            quality_score DOUBLE,
            notes VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_data_lineage (
            lineage_id BIGINT,
            product_id VARCHAR,
            upstream_product_id VARCHAR,
            transform_step VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 17 schema ready ===")


if __name__ == "__main__":
    main()