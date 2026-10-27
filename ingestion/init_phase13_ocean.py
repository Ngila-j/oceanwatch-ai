"""Phase 13 — ocean intelligence schema (SQLAlchemy / Supabase-safe)."""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, text

from db_utils import get_db_uri

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def sa_uri() -> str:
    uri = get_db_uri()
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def main():
    logger.info("=== Phase 13 ocean schema ===")
    uri = sa_uri()
    logger.info("Schema → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    eng = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})

    ddls = [
        """
        CREATE TABLE IF NOT EXISTS fact_ocean_climate_anomalies (
            as_of_date DATE,
            region_id VARCHAR,
            metric VARCHAR,
            current_value DOUBLE PRECISION,
            mean_7d DOUBLE PRECISION,
            mean_30d DOUBLE PRECISION,
            anomaly_value DOUBLE PRECISION,
            anomaly_pct DOUBLE PRECISION,
            severity VARCHAR,
            confidence_score DOUBLE PRECISION,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_ocean_risk_fusion (
            as_of_date DATE,
            region_id VARCHAR,
            sst_celsius DOUBLE PRECISION,
            chlorophyll_mg_m3 DOUBLE PRECISION,
            bloom_probability DOUBLE PRECISION,
            habitat_score DOUBLE PRECISION,
            climate_risk_score DOUBLE PRECISION,
            bloom_risk_score DOUBLE PRECISION,
            habitat_stress_score DOUBLE PRECISION,
            composite_ocean_risk DOUBLE PRECISION,
            risk_level VARCHAR,
            confidence_score DOUBLE PRECISION,
            early_warning_flag BOOLEAN,
            early_warning_message VARCHAR,
            drivers VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_environmental_warnings (
            warning_id BIGINT,
            as_of_date DATE,
            region_id VARCHAR,
            warning_type VARCHAR,
            severity VARCHAR,
            title VARCHAR,
            message VARCHAR,
            metric_value DOUBLE PRECISION,
            confidence_score DOUBLE PRECISION,
            status VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
    ]

    with eng.begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))

    logger.info("=== Phase 13 schema ready ===")
    eng.dispose()


if __name__ == "__main__":
    main()
