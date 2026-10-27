"""Phase 15 — fisheries intelligence schema (SQLAlchemy / Supabase-safe)."""

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
    logger.info("=== Phase 15 fisheries schema ===")
    uri = sa_uri()
    logger.info("Schema → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    eng = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})

    ddls = [
        """
        CREATE TABLE IF NOT EXISTS fact_fishing_effort_grid (
            cell_id VARCHAR,
            effort_date DATE,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            hours DOUBLE PRECISION,
            source VARCHAR,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_fishing_hotspots (
            hotspot_id BIGINT,
            as_of_date DATE,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            total_hours DOUBLE PRECISION,
            cell_count INTEGER,
            intensity_score DOUBLE PRECISION,
            hotspot_rank INTEGER,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_fisheries_seasonality (
            month_num INTEGER,
            month_name VARCHAR,
            total_hours DOUBLE PRECISION,
            avg_daily_hours DOUBLE PRECISION,
            observation_days INTEGER,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_illegal_fishing_risk (
            as_of_date DATE,
            region_id VARCHAR,
            gfw_hours DOUBLE PRECISION,
            fishing_vessel_ais INTEGER,
            hotspot_intensity DOUBLE PRECISION,
            anomaly_pressure DOUBLE PRECISION,
            risk_score DOUBLE PRECISION,
            risk_level VARCHAR,
            confidence_score DOUBLE PRECISION,
            drivers VARCHAR,
            disclaimer VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_fisheries_alerts (
            alert_id BIGINT,
            as_of_date DATE,
            region_id VARCHAR,
            alert_type VARCHAR,
            severity VARCHAR,
            title VARCHAR,
            message VARCHAR,
            metric_value DOUBLE PRECISION,
            status VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
    ]

    with eng.begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))

    logger.info("=== Phase 15 schema ready ===")
    eng.dispose()


if __name__ == "__main__":
    main()
