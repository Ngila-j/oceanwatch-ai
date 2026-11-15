"""Phase 14 — port intelligence schema (Mombasa). SQLAlchemy / Supabase-safe."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db_utils import get_db_uri  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def sa_uri() -> str:
    uri = get_db_uri()
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    if uri.startswith("postgresql://") and "+psycopg2" not in uri:
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    return uri


def main() -> None:
    logger.info("=== Phase 14 port schema ===")
    eng = create_engine(sa_uri(), pool_pre_ping=True, connect_args={"connect_timeout": 30})

    ddls = [
        """
        CREATE TABLE IF NOT EXISTS fact_port_performance (
            metric_date DATE,
            port_name VARCHAR,
            arrivals INTEGER,
            departures INTEGER,
            active_vessels INTEGER,
            container_vessels INTEGER,
            tankers INTEGER,
            fishing_vessels INTEGER,
            avg_waiting_hours DOUBLE PRECISION,
            congestion_index DOUBLE PRECISION,
            congestion_level VARCHAR,
            vs_30d_baseline_pct DOUBLE PRECISION,
            throughput_proxy DOUBLE PRECISION,
            balance_ratio DOUBLE PRECISION,
            performance_score DOUBLE PRECISION,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_port_congestion_forecast (
            forecast_date DATE,
            horizon_day INTEGER,
            port_name VARCHAR,
            congestion_index_pred DOUBLE PRECISION,
            congestion_level VARCHAR,
            lo DOUBLE PRECISION,
            hi DOUBLE PRECISION,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_port_arrival_forecast (
            forecast_date DATE,
            horizon_day INTEGER,
            port_name VARCHAR,
            arrivals_pred DOUBLE PRECISION,
            lo DOUBLE PRECISION,
            hi DOUBLE PRECISION,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_berth_pressure (
            as_of TIMESTAMP,
            port_name VARCHAR,
            active_vessels INTEGER,
            capacity_proxy INTEGER,
            occupancy_pct DOUBLE PRECISION,
            pressure_index DOUBLE PRECISION,
            pressure_level VARCHAR,
            arrivals_today INTEGER,
            departures_today INTEGER,
            waiting_hours DOUBLE PRECISION,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_port_ops_risk (
            as_of TIMESTAMP,
            port_name VARCHAR,
            congestion_component DOUBLE PRECISION,
            berth_component DOUBLE PRECISION,
            wait_component DOUBLE PRECISION,
            balance_component DOUBLE PRECISION,
            anomaly_component DOUBLE PRECISION,
            composite_ops_risk DOUBLE PRECISION,
            risk_level VARCHAR,
            drivers TEXT,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        # Ensure base metrics tables exist (seed_port_activity also creates these)
        """
        CREATE TABLE IF NOT EXISTS fact_port_metrics (
            metric_date DATE,
            port_name VARCHAR,
            arrivals INTEGER,
            departures INTEGER,
            active_vessels INTEGER,
            container_vessels INTEGER,
            tankers INTEGER,
            fishing_vessels INTEGER,
            avg_waiting_hours DOUBLE PRECISION,
            congestion_index DOUBLE PRECISION,
            congestion_level VARCHAR,
            vs_30d_baseline_pct DOUBLE PRECISION,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_port_activity (
            event_id BIGINT,
            event_time TIMESTAMP,
            port_name VARCHAR,
            event_type VARCHAR,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag VARCHAR,
            berth_or_anchorage VARCHAR,
            waiting_hours DOUBLE PRECISION,
            source VARCHAR,
            created_at TIMESTAMP
        )
        """,
    ]

    with eng.begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))

    logger.info("=== Phase 14 schema ready ===")
    eng.dispose()


if __name__ == "__main__":
    main()
