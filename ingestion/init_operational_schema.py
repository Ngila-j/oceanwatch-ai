"""
Create core OceanWatch operational tables in Postgres (local or Supabase).

URI resolution (first match wins):
  1. OCEANWATCH_DB_URI / DATABASE_URL env
  2. ingestion/.env
  3. db_utils.get_db_uri()
  4. local docker default
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_dotenv(path: Path = _ENV_FILE) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def get_db_uri() -> str:
    _load_dotenv()
    uri = (os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or "").strip()
    if uri:
        return uri
    try:
        from db_utils import get_db_uri as _shared

        return _shared()
    except Exception:
        pass
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def init_schema() -> None:
    uri = get_db_uri()
    safe = uri.split("@")[-1] if "@" in uri else uri
    logger.info("=== Initialising Operational Intelligence schema ===")
    logger.info("Target: ...@%s", safe)

    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    # DuckDB postgres attach works with plain postgresql:// URIs
    attach_uri = uri.replace("postgresql+psycopg2://", "postgresql://")
    con.execute(f"ATTACH '{attach_uri}' AS pg (TYPE POSTGRES);")

    # ---------- Dimensions ----------
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.dim_alert_types (
            alert_type_key INTEGER PRIMARY KEY,
            alert_type VARCHAR,
            category VARCHAR,
            description VARCHAR
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.dim_ports (
            port_key INTEGER PRIMARY KEY,
            port_name VARCHAR,
            country VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.dim_marine_zones (
            zone_key INTEGER PRIMARY KEY,
            zone_name VARCHAR,
            zone_type VARCHAR,
            min_lon DOUBLE,
            max_lon DOUBLE,
            min_lat DOUBLE,
            max_lat DOUBLE
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.dim_vessels (
            vessel_key INTEGER PRIMARY KEY,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag_country VARCHAR,
            mmsi VARCHAR,
            imo VARCHAR
        );
        """
    )

    # ---------- Facts ----------
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_alerts (
            alert_id INTEGER,
            alert_type VARCHAR,
            category VARCHAR,
            severity VARCHAR,
            created_at TIMESTAMP,
            detected_at TIMESTAMP,
            location_label VARCHAR,
            vessel_name VARCHAR,
            confidence_score DOUBLE,
            risk_score DOUBLE,
            title VARCHAR,
            description VARCHAR,
            evidence VARCHAR,
            status VARCHAR,
            resolved_at TIMESTAMP
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_ocean_anomalies (
            anomaly_id INTEGER,
            date_key DATE,
            metric VARCHAR,
            current_value DOUBLE,
            mean_7d DOUBLE,
            mean_30d DOUBLE,
            anomaly_value DOUBLE,
            anomaly_pct DOUBLE,
            severity VARCHAR,
            created_at TIMESTAMP
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_port_metrics (
            metric_date DATE,
            port_name VARCHAR,
            arrivals INTEGER,
            departures INTEGER,
            active_vessels INTEGER,
            container_vessels INTEGER,
            tankers INTEGER,
            fishing_vessels INTEGER,
            avg_waiting_hours DOUBLE,
            congestion_index DOUBLE,
            congestion_level VARCHAR,
            vs_30d_baseline_pct DOUBLE,
            created_at TIMESTAMP
        );
        """
    )

    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_fishing_risk (
            risk_id INTEGER,
            event_time TIMESTAMP,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag_country VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE,
            risk_score DOUBLE,
            confidence_score DOUBLE,
            evidence VARCHAR,
            status VARCHAR,
            created_at TIMESTAMP
        );
        """
    )

    # Seed basic dimensions (idempotent-ish)
    con.execute("DELETE FROM pg.public.dim_ports;")
    con.execute(
        """
        INSERT INTO pg.public.dim_ports VALUES
        (1, 'Mombasa', 'Kenya', -4.0435, 39.6682);
        """
    )

    con.execute("DELETE FROM pg.public.dim_marine_zones;")
    con.execute(
        """
        INSERT INTO pg.public.dim_marine_zones VALUES
        (1, 'Kenya EEZ Monitoring Box', 'EEZ', 39.0, 45.0, -5.0, 2.0),
        (2, 'Sample MPA Zone', 'MPA', 40.5, 41.5, -3.0, -2.0);
        """
    )

    con.execute("DELETE FROM pg.public.dim_alert_types;")
    con.execute(
        """
        INSERT INTO pg.public.dim_alert_types VALUES
        (1, 'SST_ANOMALY', 'COASTAL', 'Sea Surface Temperature anomaly'),
        (2, 'CHL_ANOMALY', 'COASTAL', 'Chlorophyll anomaly / bloom risk'),
        (3, 'PORT_CONGESTION', 'PORT', 'Port congestion elevated'),
        (4, 'FISHING_RISK', 'FISHING', 'Potential anomalous fishing behaviour'),
        (5, 'SYSTEM', 'SYSTEM', 'System heartbeat / status');
        """
    )

    con.close()
    logger.info("=== Schema initialisation completed ===")


if __name__ == "__main__":
    init_schema()
