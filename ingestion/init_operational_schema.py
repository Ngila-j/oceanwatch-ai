import os
import logging
import duckdb

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        host, port = "postgres", 5432
    else:
        host, port = "localhost", 5433
    return f"postgresql://postgres:password@{host}:{port}/oceanwatch_db"


def init_schema():
    logger.info("=== Initialising Operational Intelligence schema ===")
    con = duckdb.connect()
    con.execute("INSTALL postgres; LOAD postgres;")
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES);")

    # ---------- Dimensions ----------
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.dim_alert_types (
            alert_type_key INTEGER PRIMARY KEY,
            alert_type VARCHAR,
            category VARCHAR,          -- PORT, FISHING, COASTAL, SYSTEM
            description VARCHAR
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.dim_ports (
            port_key INTEGER PRIMARY KEY,
            port_name VARCHAR,
            country VARCHAR,
            latitude DOUBLE,
            longitude DOUBLE
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.dim_marine_zones (
            zone_key INTEGER PRIMARY KEY,
            zone_name VARCHAR,
            zone_type VARCHAR,         -- EEZ, MPA, FISHING_ZONE, RESTRICTED
            min_lon DOUBLE,
            max_lon DOUBLE,
            min_lat DOUBLE,
            max_lat DOUBLE
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.dim_vessels (
            vessel_key INTEGER PRIMARY KEY,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag_country VARCHAR,
            mmsi VARCHAR,
            imo VARCHAR
        );
    """)

    # ---------- Facts ----------
    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_alerts (
            alert_id INTEGER,
            alert_type VARCHAR,
            category VARCHAR,
            severity VARCHAR,              -- INFO, WATCH, ELEVATED, CRITICAL
            created_at TIMESTAMP,
            detected_at TIMESTAMP,
            location_label VARCHAR,
            vessel_name VARCHAR,
            confidence_score DOUBLE,       -- 0-100
            risk_score DOUBLE,             -- 0-100
            title VARCHAR,
            description VARCHAR,
            evidence VARCHAR,              -- JSON-like text of reasons
            status VARCHAR,                -- OPEN, UNDER_REVIEW, RESOLVED
            resolved_at TIMESTAMP
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS pg.public.fact_ocean_anomalies (
            anomaly_id INTEGER,
            date_key DATE,
            metric VARCHAR,                -- SST, CHL
            current_value DOUBLE,
            mean_7d DOUBLE,
            mean_30d DOUBLE,
            anomaly_value DOUBLE,
            anomaly_pct DOUBLE,
            severity VARCHAR,
            created_at TIMESTAMP
        );
    """)

    con.execute("""
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
            congestion_index DOUBLE,       -- 0-100
            congestion_level VARCHAR,      -- LOW, MODERATE, HIGH
            vs_30d_baseline_pct DOUBLE,
            created_at TIMESTAMP
        );
    """)

    con.execute("""
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
    """)

    # Seed basic dimensions
    con.execute("DELETE FROM pg.public.dim_ports;")
    con.execute("""
        INSERT INTO pg.public.dim_ports VALUES
        (1, 'Mombasa', 'Kenya', -4.0435, 39.6682);
    """)

    con.execute("DELETE FROM pg.public.dim_marine_zones;")
    con.execute("""
        INSERT INTO pg.public.dim_marine_zones VALUES
        (1, 'Kenya EEZ Monitoring Box', 'EEZ', 39.0, 45.0, -5.0, 2.0),
        (2, 'Sample MPA Zone', 'MPA', 40.5, 41.5, -3.0, -2.0);
    """)

    con.execute("DELETE FROM pg.public.dim_alert_types;")
    con.execute("""
        INSERT INTO pg.public.dim_alert_types VALUES
        (1, 'SST_ANOMALY', 'COASTAL', 'Sea Surface Temperature anomaly'),
        (2, 'CHL_ANOMALY', 'COASTAL', 'Chlorophyll anomaly / bloom risk'),
        (3, 'PORT_CONGESTION', 'PORT', 'Port congestion elevated'),
        (4, 'FISHING_RISK', 'FISHING', 'Potential anomalous fishing behaviour'),
        (5, 'SYSTEM', 'SYSTEM', 'System heartbeat / status');
    """)

    con.close()
    logger.info("=== Schema initialisation completed ===")


if __name__ == "__main__":
    init_schema()