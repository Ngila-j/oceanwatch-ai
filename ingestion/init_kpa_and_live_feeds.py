"""Schema: KPA 14-day shipping movement + free live feed tables."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db_utils import get_db_uri, sa_uri  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("init_kpa_live")

DDL = [
    """
    CREATE TABLE IF NOT EXISTS fact_kpa_shipping_movement (
        id              BIGSERIAL PRIMARY KEY,
        report_date     DATE,
        vessel_name     TEXT,
        voyage          TEXT,
        agent           TEXT,
        eta             TIMESTAMPTZ,
        etd             TIMESTAMPTZ,
        berth           TEXT,
        cargo           TEXT,
        loa_m           DOUBLE PRECISION,
        draft_m         DOUBLE PRECISION,
        grt             DOUBLE PRECISION,
        flag            TEXT,
        movement_type   TEXT,
        origin          TEXT,
        destination     TEXT,
        raw_line        TEXT,
        source_url      TEXT,
        source_file     TEXT,
        content_hash    TEXT,
        ingested_at     TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_kpa_ship_mv_lookup
      ON fact_kpa_shipping_movement (report_date, vessel_name)
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_kpa_ingest_log (
        id              BIGSERIAL PRIMARY KEY,
        report_date     DATE,
        source_file     TEXT,
        content_hash    TEXT,
        row_count       INTEGER,
        status          TEXT,
        message         TEXT,
        ingested_at     TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_live_weather (
        id              BIGSERIAL PRIMARY KEY,
        source          TEXT NOT NULL,
        location        TEXT NOT NULL,
        lat             DOUBLE PRECISION,
        lon             DOUBLE PRECISION,
        observed_at     TIMESTAMPTZ NOT NULL,
        temp_c          DOUBLE PRECISION,
        humidity_pct    DOUBLE PRECISION,
        wind_ms         DOUBLE PRECISION,
        wind_dir_deg    DOUBLE PRECISION,
        precip_mm       DOUBLE PRECISION,
        pressure_hpa    DOUBLE PRECISION,
        cloud_pct       DOUBLE PRECISION,
        weather_code    INTEGER,
        raw_json        JSONB,
        ingested_at     TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_live_weather_obs
      ON fact_live_weather (location, observed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_live_marine (
        id              BIGSERIAL PRIMARY KEY,
        source          TEXT NOT NULL,
        location        TEXT NOT NULL,
        lat             DOUBLE PRECISION,
        lon             DOUBLE PRECISION,
        observed_at     TIMESTAMPTZ NOT NULL,
        wave_height_m   DOUBLE PRECISION,
        wave_period_s   DOUBLE PRECISION,
        wave_dir_deg    DOUBLE PRECISION,
        swell_height_m  DOUBLE PRECISION,
        swell_period_s  DOUBLE PRECISION,
        swell_dir_deg   DOUBLE PRECISION,
        wind_wave_m     DOUBLE PRECISION,
        sea_temp_c      DOUBLE PRECISION,
        raw_json        JSONB,
        ingested_at     TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_live_marine_obs
      ON fact_live_marine (location, observed_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_live_earthquakes (
        id              TEXT PRIMARY KEY,
        source          TEXT NOT NULL DEFAULT 'USGS',
        event_time      TIMESTAMPTZ,
        lat             DOUBLE PRECISION,
        lon             DOUBLE PRECISION,
        depth_km        DOUBLE PRECISION,
        mag             DOUBLE PRECISION,
        place           TEXT,
        tsunami         INTEGER,
        url             TEXT,
        raw_json        JSONB,
        ingested_at     TIMESTAMPTZ DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_live_feed_runs (
        id              BIGSERIAL PRIMARY KEY,
        feed_name       TEXT NOT NULL,
        status          TEXT NOT NULL,
        rows_upserted   INTEGER DEFAULT 0,
        message         TEXT,
        started_at      TIMESTAMPTZ,
        finished_at     TIMESTAMPTZ DEFAULT NOW()
    )
    """,
]


def main() -> int:
    eng = create_engine(sa_uri(get_db_uri()), pool_pre_ping=True)
    with eng.begin() as conn:
        for ddl in DDL:
            try:
                conn.execute(text(ddl))
            except Exception as exc:  # noqa: BLE001
                # unique index with COALESCE may fail on some PG; fall back
                log.warning("DDL note: %s", exc)
                if "uq_kpa_ship_mv" in ddl:
                    conn.execute(
                        text(
                            """
                            CREATE INDEX IF NOT EXISTS ix_kpa_ship_mv_lookup
                              ON fact_kpa_shipping_movement (report_date, vessel_name)
                            """
                        )
                    )
    log.info("KPA + live feed schema ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
