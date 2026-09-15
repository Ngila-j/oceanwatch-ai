"""Phase 25 — partner access keys & audit trail schema."""

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
    logger.info("=== Phase 25 access schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    for t in (
        "dim_api_clients",
        "dim_api_keys",
        "fact_api_usage",
        "fact_audit_log",
    ):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.dim_api_clients (
            client_id VARCHAR PRIMARY KEY,
            client_name VARCHAR,
            organization VARCHAR,
            tier VARCHAR,
            status VARCHAR,
            contact_email VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.dim_api_keys (
            key_id VARCHAR PRIMARY KEY,
            client_id VARCHAR,
            key_prefix VARCHAR,
            key_hash VARCHAR,
            scopes VARCHAR,
            rate_limit_per_day INTEGER,
            status VARCHAR,
            expires_at TIMESTAMP,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_api_usage (
            usage_id BIGINT,
            client_id VARCHAR,
            key_id VARCHAR,
            endpoint VARCHAR,
            method VARCHAR,
            status_code INTEGER,
            latency_ms DOUBLE,
            region_id VARCHAR,
            requested_at TIMESTAMP,
            model_version VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_audit_log (
            audit_id BIGINT,
            actor VARCHAR,
            action VARCHAR,
            entity_type VARCHAR,
            entity_id VARCHAR,
            detail VARCHAR,
            region_id VARCHAR,
            created_at TIMESTAMP,
            model_version VARCHAR
        )
        """
    )
    logger.info("=== Phase 25 schema ready ===")


if __name__ == "__main__":
    main()