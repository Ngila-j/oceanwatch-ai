"""Phase 19 — vessel state & events schema (SQLAlchemy / Supabase-safe)."""

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
    logger.info("=== Phase 19 maritime events schema ===")
    uri = sa_uri()
    logger.info("Schema → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    eng = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})

    ddls = [
        """
        CREATE TABLE IF NOT EXISTS fact_vessel_state (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            last_lat DOUBLE PRECISION,
            last_lon DOUBLE PRECISION,
            last_sog DOUBLE PRECISION,
            last_cog DOUBLE PRECISION,
            last_seen TIMESTAMP,
            state_label VARCHAR,
            loitering_flag BOOLEAN,
            near_port_flag BOOLEAN,
            mpa_flag BOOLEAN,
            risk_score DOUBLE PRECISION,
            source VARCHAR,
            region_id VARCHAR,
            country_id VARCHAR,
            model_version VARCHAR,
            updated_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_vessel_events (
            event_id BIGINT,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            event_type VARCHAR,
            event_time TIMESTAMP,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            severity VARCHAR,
            confidence DOUBLE PRECISION,
            evidence VARCHAR,
            region_id VARCHAR,
            country_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_vessel_movements (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            positions_count INTEGER,
            avg_sog DOUBLE PRECISION,
            max_sog DOUBLE PRECISION,
            min_sog DOUBLE PRECISION,
            track_hours DOUBLE PRECISION,
            distance_km DOUBLE PRECISION,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            region_id VARCHAR,
            country_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
    ]

    with eng.begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))

    logger.info("=== Phase 19 schema ready ===")
    eng.dispose()


if __name__ == "__main__":
    main()
