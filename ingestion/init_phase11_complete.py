"""Phase 11 complete schema: events, risks, freshness, provenance."""

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
    logger.info("=== Phase 11 complete schema ===")
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
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.data_freshness (
            source_key VARCHAR,
            source_name VARCHAR,
            last_timestamp TIMESTAMP,
            age_minutes DOUBLE,
            status VARCHAR,
            record_count BIGINT,
            notes VARCHAR,
            checked_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.data_provenance (
            metric_key VARCHAR,
            metric_label VARCHAR,
            value_text VARCHAR,
            source_system VARCHAR,
            dataset_name VARCHAR,
            observed_at TIMESTAMP,
            pipeline_version VARCHAR,
            quality_flag VARCHAR,
            region_id VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.spatial_intelligence (
            metric_key VARCHAR,
            metric_label VARCHAR,
            metric_value DOUBLE,
            unit VARCHAR,
            region_id VARCHAR,
            details VARCHAR,
            model_version VARCHAR,
            computed_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 11 schema ready ===")


if __name__ == "__main__":
    main()