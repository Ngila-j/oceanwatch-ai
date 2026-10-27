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
            last_seen TIMESTAMP,
            position_count BIGINT,
            track_hours DOUBLE PRECISION,
            speed_mean DOUBLE PRECISION,
            speed_max DOUBLE PRECISION,
            low_speed_ratio DOUBLE PRECISION,
            turn_rate_proxy DOUBLE PRECISION,
            track_efficiency DOUBLE PRECISION,
            behaviour_score DOUBLE PRECISION,
            behaviour_level VARCHAR,
            risk_score DOUBLE PRECISION,
            confidence_score DOUBLE PRECISION,
            in_kenya_box BOOLEAN,
            near_mombasa BOOLEAN,
            mpa_interaction_flag BOOLEAN,
            geofence_hits INTEGER,
            evidence VARCHAR,
            model_version VARCHAR,
            region_id VARCHAR,
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
            notes VARCHAR
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_geofence_events (
            event_id BIGINT,
            mmsi VARCHAR,
            vessel_name VARCHAR,
            fence_id VARCHAR,
            fence_name VARCHAR,
            event_time TIMESTAMP,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            sog DOUBLE PRECISION,
            region_id VARCHAR,
            model_version VARCHAR,
            created_at TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS fact_vessel_track_points (
            mmsi VARCHAR,
            event_time TIMESTAMP,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            sog DOUBLE PRECISION,
            cog DOUBLE PRECISION,
            vessel_name VARCHAR,
            source VARCHAR,
            created_at TIMESTAMP
        )
        """,
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
            "kenya_eez",
            "Primary analysis box",
        ),
        (
            "MOMBASA_APPROACH",
            "Mombasa approach",
            "PORT",
            -4.20,
            -3.90,
            39.50,
            39.85,
            "kenya_eez",
            "Port approach watch box",
        ),
        (
            "MPA_PROXY_DEMO",
            "MPA proxy (demo)",
            "MPA",
            -3.50,
            -2.80,
            40.00,
            40.60,
            "kenya_eez",
            "Demo engineering fence — not official MPA",
        ),
        (
            "LAMU_CHANNEL",
            "Lamu channel watch",
            "CHANNEL",
            -2.40,
            -1.90,
            40.70,
            41.20,
            "kenya_eez",
            "Northern channel watch",
        ),
    ]

    with eng.begin() as conn:
        for ddl in ddls:
            conn.execute(text(ddl))

        n = conn.execute(text("SELECT COUNT(*) FROM dim_geofences")).scalar() or 0
        if n == 0:
            for row in geofence_seed:
                conn.execute(
                    text(
                        """
                        INSERT INTO dim_geofences
                        (fence_id, fence_name, fence_type, min_lat, max_lat, min_lon, max_lon, region_id, notes)
                        VALUES (:fid, :fn, :ft, :min_lat, :max_lat, :min_lon, :max_lon, :rid, :notes)
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

    logger.info("=== Phase 12 schema ready ===")
    eng.dispose()


if __name__ == "__main__":
    main()
