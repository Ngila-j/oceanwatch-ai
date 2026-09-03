"""Phase 19 — vessel state & events schema."""

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
    logger.info("=== Phase 19 maritime events schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    for t in ("fact_vessel_events", "fact_vessel_state", "fact_vessel_movements"):
        con.execute(f"DROP TABLE IF EXISTS pg.public.{t} CASCADE")

    con.execute(
        """
        CREATE TABLE pg.public.fact_vessel_state (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            last_lat DOUBLE,
            last_lon DOUBLE,
            last_sog DOUBLE,
            last_cog DOUBLE,
            last_seen TIMESTAMP,
            state_label VARCHAR,
            in_port_approach BOOLEAN,
            loitering_flag BOOLEAN,
            region_id VARCHAR,
            country_id VARCHAR,
            source VARCHAR,
            model_version VARCHAR,
            updated_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_vessel_events (
            event_id BIGINT,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            event_type VARCHAR,
            event_time TIMESTAMP,
            lat DOUBLE,
            lon DOUBLE,
            severity VARCHAR,
            evidence VARCHAR,
            region_id VARCHAR,
            country_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE pg.public.fact_vessel_movements (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            positions_count INTEGER,
            avg_sog DOUBLE,
            max_sog DOUBLE,
            min_sog DOUBLE,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    logger.info("=== Phase 19 schema ready ===")


if __name__ == "__main__":
    main()