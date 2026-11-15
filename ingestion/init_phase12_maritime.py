"""Phase 12 — maritime intelligence schema (SQLAlchemy / Supabase-safe)."""

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
    logger.info("=== Phase 12 maritime schema ===")
    uri = sa_uri()
    logger.info("Schema → ...@%s", uri.split("@")[-1] if "@" in uri else uri)
    eng = create_engine(uri, pool_pre_ping=True, connect_args={"connect_timeout": 30})

    ddls = [
        """
        CREATE TABLE IF NOT EXISTS dim_vessels_maritime (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            flag VARCHAR,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            position_count BIGINT,
            source VARCHAR,
            updated_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_vessel_profiles (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            last_lat DOUBLE PRECISION,
            last_lon DOUBLE PRECISION,
            last_sog DOUBLE PRECISION,
            last_cog DOUBLE PRECISION,
            first_seen TIMESTAMP,
            last_seen TIMESTAMP,
            position_count BIGINT,
            track_hours DOUBLE PRECISION,
            hours_observed DOUBLE PRECISION,
            speed_mean DOUBLE PRECISION,
            speed_max DOUBLE PRECISION,
            low_speed_ratio DOUBLE PRECISION,
            turn_rate_proxy DOUBLE PRECISION,
            track_efficiency DOUBLE PRECISION,
            distance_nm DOUBLE PRECISION,
            behaviour_score DOUBLE PRECISION,
            behaviour_level VARCHAR,
            risk_score DOUBLE PRECISION,
            risk_tier VARCHAR,
            confidence_score DOUBLE PRECISION,
            anomaly_score DOUBLE PRECISION,
            in_kenya_box BOOLEAN,
            in_kenya_eez BOOLEAN,
            near_mombasa BOOLEAN,
            near_port BOOLEAN,
            mpa_interaction_flag BOOLEAN,
            geofence_hits INTEGER,
            evidence TEXT,
            model_version VARCHAR,
            region_id VARCHAR,
            source VARCHAR,
            computed_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS dim_geofences (
            fence_id VARCHAR,
            fence_name VARCHAR,
            fence_type VARCHAR,
            min_lat DOUBLE PRECISION,
            max_lat DOUBLE PRECISION,
            min_lon DOUBLE PRECISION,
            max_lon DOUBLE PRECISION,
            region_id VARCHAR,
            notes VARCHAR,
            active BOOLEAN DEFAULT TRUE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_geofence_events (
            event_id BIGINT,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            fence_id VARCHAR,
            fence_name VARCHAR,
            event_type VARCHAR,
            event_time TIMESTAMP,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            sog DOUBLE PRECISION,
            region_id VARCHAR,
            model_version VARCHAR,
            source VARCHAR,
            ingested_at TIMESTAMP,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_vessel_track_points (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            event_time TIMESTAMP,
            ts TIMESTAMP,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            sog DOUBLE PRECISION,
            cog DOUBLE PRECISION,
            source VARCHAR,
            ingested_at TIMESTAMP,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_vessel_behaviour_scores (
            mmsi VARCHAR,
            vessel_name VARCHAR,
            vessel_type VARCHAR,
            window_start TIMESTAMP,
            window_end TIMESTAMP,
            risk_score DOUBLE PRECISION,
            loitering_score DOUBLE PRECISION,
            dark_score DOUBLE PRECISION,
            mpa_score DOUBLE PRECISION,
            speed_anomaly_score DOUBLE PRECISION,
            evidence TEXT,
            computed_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_vessel_anomalies (
            mmsi VARCHAR,
            detected_at TIMESTAMP,
            anomaly_type VARCHAR,
            score DOUBLE PRECISION,
            severity VARCHAR,
            evidence TEXT,
            lat DOUBLE PRECISION,
            lon DOUBLE PRECISION,
            source VARCHAR,
            created_at TIMESTAMP
        )
        """,
    ]

    alters = [
        "ALTER TABLE dim_geofences ADD COLUMN IF NOT EXISTS active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS first_seen TIMESTAMP",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS near_mombasa BOOLEAN",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS near_port BOOLEAN",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS mpa_interaction_flag BOOLEAN",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS turn_rate_proxy DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS evidence TEXT",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS risk_score DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS risk_tier VARCHAR",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS anomaly_score DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS in_kenya_box BOOLEAN",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS in_kenya_eez BOOLEAN",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS distance_nm DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_profiles ADD COLUMN IF NOT EXISTS hours_observed DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_track_points ADD COLUMN IF NOT EXISTS ts TIMESTAMP",
        "ALTER TABLE fact_vessel_track_points ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_track_points ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_track_points ADD COLUMN IF NOT EXISTS event_time TIMESTAMP",
        "ALTER TABLE fact_vessel_track_points ADD COLUMN IF NOT EXISTS latitude DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_track_points ADD COLUMN IF NOT EXISTS longitude DOUBLE PRECISION",
        "ALTER TABLE fact_vessel_track_points ADD COLUMN IF NOT EXISTS vessel_name VARCHAR",
        "ALTER TABLE fact_vessel_track_points ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP",
        "ALTER TABLE fact_geofence_events ADD COLUMN IF NOT EXISTS event_type VARCHAR",
        "ALTER TABLE fact_geofence_events ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION",
        "ALTER TABLE fact_geofence_events ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION",
        "ALTER TABLE fact_geofence_events ADD COLUMN IF NOT EXISTS source VARCHAR",
        "ALTER TABLE fact_geofence_events ADD COLUMN IF NOT EXISTS ingested_at TIMESTAMP",
    ]

    geofence_seed = [
        (
            "KE_EEZ_BOX",
            "Kenya EEZ analysis box",
            "ANALYSIS",
            -4.8,
            -1.5,
            39.0,
            44.0,
            "KE-EEZ",
            "Primary analysis box",
        ),
        (
            "KE_MOMBASA_PORT",
            "Mombasa port approaches",
            "PORT",
            -4.2,
            -3.9,
            39.5,
            39.8,
            "KE-MSA",
            "Port approaches",
        ),
        (
            "KE_LAMU_MPA",
            "Lamu / Kiunga MPA watch",
            "MPA",
            -2.4,
            -1.6,
            40.7,
            41.4,
            "KE-LAMU",
            "MPA / sensitive coast",
        ),
        (
            "KE_SHIMONI",
            "Shimoni / Wasini approaches",
            "PORT",
            -4.7,
            -4.5,
            39.3,
            39.5,
            "KE-SHIM",
            "Southern channel watch",
        ),
    ]

    with eng.begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))
        for stmt in alters:
            try:
                conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001
                logger.debug("alter skip: %s (%s)", stmt, exc)

        n = conn.execute(text("SELECT COUNT(*) FROM dim_geofences")).scalar() or 0
        if n == 0:
            for row in geofence_seed:
                conn.execute(
                    text(
                        """
                        INSERT INTO dim_geofences
                        (fence_id, fence_name, fence_type, min_lat, max_lat, min_lon, max_lon, region_id, notes, active)
                        VALUES (:fid, :fn, :ft, :min_lat, :max_lat, :min_lon, :max_lon, :rid, :notes, TRUE)
                        """
                    ),
                    {
                        "fid": row[0],
                        "fn": row[1],
                        "ft": row[2],
                        "min_lat": row[3],
                        "max_lat": row[4],
                        "min_lon": row[5],
                        "max_lon": row[6],
                        "rid": row[7],
                        "notes": row[8],
                    },
                )
            logger.info("Seeded %s geofences", len(geofence_seed))
        else:
            logger.info("dim_geofences already has %s rows", n)
            try:
                conn.execute(
                    text("UPDATE dim_geofences SET active = TRUE WHERE active IS NULL")
                )
            except Exception:  # noqa: BLE001
                pass

    logger.info("=== Phase 12 schema ready ===")
    eng.dispose()


if __name__ == "__main__":
    main()
