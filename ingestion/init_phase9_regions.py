"""Phase 9 — dim_regions + source registry + index table."""
import os
import logging
from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

REGIONS = [
    ("kenya_eez", "Kenya EEZ / Mombasa", "Kenya", 39.0, 45.0, -5.0, 2.0, True, "ACTIVE"),
    ("tanzania_coast", "Tanzania coastal EEZ", "Tanzania", 38.5, 42.0, -11.0, -4.5, False, "PLANNED"),
    ("seychelles", "Seychelles EEZ (core box)", "Seychelles", 55.0, 57.5, -6.0, -3.5, False, "PLANNED"),
    ("n_mozambique_channel", "Northern Mozambique Channel", "Multi-country", 40.0, 48.0, -15.0, -10.0, False, "PLANNED"),
]


def get_db_uri() -> str:
    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def main():
    logger.info("=== Phase 9 regional schema ===")
    engine = create_engine(get_db_uri())

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dim_regions (
                region_id VARCHAR PRIMARY KEY,
                region_name VARCHAR NOT NULL,
                country VARCHAR,
                min_lon DOUBLE PRECISION,
                max_lon DOUBLE PRECISION,
                min_lat DOUBLE PRECISION,
                max_lat DOUBLE PRECISION,
                is_primary BOOLEAN DEFAULT FALSE,
                status VARCHAR DEFAULT 'PLANNED',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS dim_data_sources (
                source_id VARCHAR PRIMARY KEY,
                source_name VARCHAR NOT NULL,
                category VARCHAR,
                coverage VARCHAR,
                access_type VARCHAR,
                status VARCHAR,
                partner VARCHAR,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS fact_wio_intelligence_index (
                index_date DATE NOT NULL,
                region_id VARCHAR NOT NULL,
                ocean_score DOUBLE PRECISION,
                port_score DOUBLE PRECISION,
                fishing_score DOUBLE PRECISION,
                environmental_score DOUBLE PRECISION,
                security_score DOUBLE PRECISION,
                overall_index DOUBLE PRECISION,
                drivers TEXT,
                methodology_version VARCHAR DEFAULT 'v0.1',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (index_date, region_id)
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS raw_local_tides (
                observation_time TIMESTAMP,
                station_id VARCHAR,
                station_name VARCHAR,
                tide_height_m DOUBLE PRECISION,
                source VARCHAR,
                region_id VARCHAR,
                loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS raw_kmd_weather (
                observation_time TIMESTAMP,
                station_id VARCHAR,
                location_name VARCHAR,
                wind_speed_ms DOUBLE PRECISION,
                wind_dir_deg DOUBLE PRECISION,
                rainfall_mm DOUBLE PRECISION,
                air_temp_c DOUBLE PRECISION,
                source VARCHAR DEFAULT 'KMD_STUB',
                region_id VARCHAR,
                loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS raw_fisheries_catch (
                catch_date DATE,
                landing_site VARCHAR,
                species_group VARCHAR,
                catch_kg DOUBLE PRECISION,
                boats_reported INTEGER,
                source VARCHAR,
                region_id VARCHAR,
                loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.execute(text("DELETE FROM dim_regions;"))
        for r in REGIONS:
            conn.execute(
                text("""
                    INSERT INTO dim_regions
                    (region_id, region_name, country, min_lon, max_lon, min_lat, max_lat, is_primary, status)
                    VALUES (:id, :name, :country, :min_lon, :max_lon, :min_lat, :max_lat, :primary, :status)
                """),
                {
                    "id": r[0], "name": r[1], "country": r[2],
                    "min_lon": r[3], "max_lon": r[4], "min_lat": r[5], "max_lat": r[6],
                    "primary": r[7], "status": r[8],
                },
            )

        conn.execute(text("DELETE FROM dim_data_sources;"))
        sources = [
            ("noaa_tides", "NOAA CO-OPS tides", "ocean", "global stations", "open_api", "ACTIVE", None, "Sample station used for pipeline"),
            ("copernicus_sst_chl", "Copernicus Marine SST/CHL", "ocean", "WIO boxes", "open_api", "ACTIVE", None, "Primary environmental source"),
            ("gfw_effort", "Global Fishing Watch effort", "fishing", "global", "api_token", "ACTIVE", "GFW", "CC BY-NC 4.0"),
            ("ais_sample", "AIS sample tracks", "ais", "kenya_box", "synthetic", "ACTIVE", None, "Demo continuity"),
            ("aisstream", "AISStream live", "ais", "sparse_wio", "api_token", "PARTIAL", None, "Kenya coverage sparse"),
            ("local_tides", "Local tide gauges", "ocean", "kenya", "partner", "PLANNED", "KPA/KMD", "Needs local partnership"),
            ("kmd_weather", "Kenya Meteorological Department", "weather", "kenya", "partner", "STUB", "KMD", "File/API adapter ready"),
            ("fisheries_catch", "Regional fisheries landings", "fishing", "kenya", "partner", "STUB", "KMFRI/BMU", "Where data sharing allows"),
        ]
        for s in sources:
            conn.execute(
                text("""
                    INSERT INTO dim_data_sources
                    (source_id, source_name, category, coverage, access_type, status, partner, notes)
                    VALUES (:id, :name, :cat, :cov, :access, :status, :partner, :notes)
                """),
                {
                    "id": s[0], "name": s[1], "cat": s[2], "cov": s[3],
                    "access": s[4], "status": s[5], "partner": s[6], "notes": s[7],
                },
            )

    logger.info("=== Phase 9 schema ready ===")


if __name__ == "__main__":
    main()