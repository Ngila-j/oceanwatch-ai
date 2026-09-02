"""Phase 12 — maritime intelligence schema (Kenya)."""

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
    logger.info("=== Phase 12 maritime schema ===")
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")

    # Dedicated table — do NOT reuse legacy dim_vessels (different schema)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.dim_vessels_maritime (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag VARCHAR,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            source VARCHAR,
            updated_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_vessel_profiles (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            last_lat DOUBLE,
            last_lon DOUBLE,
            last_sog DOUBLE,
            last_cog DOUBLE,
            last_seen TIMESTAMP,
            position_count BIGINT,
            track_hours DOUBLE,
            speed_mean DOUBLE,
            speed_max DOUBLE,
            low_speed_ratio DOUBLE,
            turn_rate_proxy DOUBLE,
            track_efficiency DOUBLE,
            behaviour_score DOUBLE,
            behaviour_level VARCHAR,
            risk_score DOUBLE,
            confidence_score DOUBLE,
            in_kenya_box BOOLEAN,
            near_mombasa BOOLEAN,
            mpa_interaction_flag BOOLEAN,
            geofence_hits BIGINT,
            evidence VARCHAR,
            model_version VARCHAR,
            region_id VARCHAR,
            computed_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.dim_geofences (
            fence_id VARCHAR,
            fence_name VARCHAR,
            fence_type VARCHAR,
            min_lat DOUBLE,
            max_lat DOUBLE,
            min_lon DOUBLE,
            max_lon DOUBLE,
            region_id VARCHAR,
            notes VARCHAR
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_geofence_events (
            event_id BIGINT,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            fence_id VARCHAR,
            fence_name VARCHAR,
            event_kind VARCHAR,
            event_time TIMESTAMP,
            latitude DOUBLE,
            longitude DOUBLE,
            sog DOUBLE,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS pg.public.fact_vessel_track_points (
            mmsi VARCHAR,
            event_time TIMESTAMP,
            latitude DOUBLE,
            longitude DOUBLE,
            sog DOUBLE,
            cog DOUBLE,
            source VARCHAR,
            in_kenya_box BOOLEAN,
            near_mombasa BOOLEAN
        )
        """
    )

    con.execute("DELETE FROM pg.public.dim_geofences")
    con.execute(
        """
        INSERT INTO pg.public.dim_geofences VALUES
        ('kenya_wio_box', 'Kenya/WIO monitoring box', 'EEZ_MONITOR', -6.0, 3.0, 38.0, 46.0, 'kenya_eez', 'Primary analysis box'),
        ('mombasa_approach', 'Mombasa port approach', 'PORT', -4.40, -3.70, 39.40, 40.00, 'kenya_eez', 'Approx approaches'),
        ('mpa_demo_malindi', 'Demo coastal MPA (proxy)', 'MPA_PROXY', -3.50, -2.80, 40.00, 40.60, 'kenya_eez', 'Placeholder — not official MPA boundary')
        """
    )
    logger.info("=== Phase 12 schema ready ===")


if __name__ == "__main__":
    main()