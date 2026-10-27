"""Phase 18 — regional hierarchy schema (SQLAlchemy / Supabase-safe)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from db_utils import get_db_uri as _shared_uri
except ImportError:
    _shared_uri = None  # type: ignore


def get_db_uri() -> str:
    if _shared_uri is not None:
        uri = (_shared_uri() or "").strip()
        if uri:
            return uri
    try:
        from dotenv import load_dotenv

        load_dotenv(_ROOT / ".env")
    except ImportError:
        pass
    uri = (os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or "").strip()
    if uri:
        return uri
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def _engine(uri: str | None = None) -> Engine:
    raw = (uri or get_db_uri()).strip()
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg2://", 1)
    connect_args: dict = {"connect_timeout": 20}
    if "supabase" in raw or "pooler" in raw or "sslmode=" in raw:
        connect_args["sslmode"] = "require"
    return create_engine(raw, pool_pre_ping=True, connect_args=connect_args, pool_size=1, max_overflow=0)


DDL_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS dim_countries (
        country_id   VARCHAR(8) PRIMARY KEY,
        country_name TEXT NOT NULL,
        iso3         VARCHAR(3),
        status       VARCHAR(32) DEFAULT 'PLANNED',
        notes        TEXT,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_regions (
        region_id     VARCHAR(64) PRIMARY KEY,
        country_id    VARCHAR(8),
        region_name   TEXT NOT NULL,
        region_type   VARCHAR(32),
        min_lat       DOUBLE PRECISION,
        max_lat       DOUBLE PRECISION,
        min_lon       DOUBLE PRECISION,
        max_lon       DOUBLE PRECISION,
        is_primary    BOOLEAN DEFAULT FALSE,
        status        VARCHAR(32) DEFAULT 'PLANNED',
        notes         TEXT,
        country       TEXT,
        model_version VARCHAR(64),
        created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_ports_ref (
        port_id     VARCHAR(64) PRIMARY KEY,
        country_id  VARCHAR(8),
        region_id   VARCHAR(64),
        port_name   TEXT NOT NULL,
        lat         DOUBLE PRECISION,
        lon         DOUBLE PRECISION,
        unlocode    VARCHAR(16),
        status      VARCHAR(32) DEFAULT 'PLANNED',
        notes       TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_marine_zones (
        zone_id     VARCHAR(64) PRIMARY KEY,
        zone_key    VARCHAR(64),
        country_id  VARCHAR(8),
        region_id   VARCHAR(64),
        zone_name   TEXT NOT NULL,
        zone_type   VARCHAR(64),
        min_lat     DOUBLE PRECISION,
        max_lat     DOUBLE PRECISION,
        min_lon     DOUBLE PRECISION,
        max_lon     DOUBLE PRECISION,
        status      VARCHAR(32) DEFAULT 'DEMO',
        notes       TEXT,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

# Add columns if an older slim table already exists (no DROP by default).
ALTER_COLUMNS = [
    ("dim_regions", "region_type", "VARCHAR(32)"),
    ("dim_regions", "notes", "TEXT"),
    ("dim_regions", "country", "TEXT"),
    ("dim_regions", "model_version", "VARCHAR(64)"),
    ("dim_regions", "country_id", "VARCHAR(8)"),
    ("dim_regions", "min_lat", "DOUBLE PRECISION"),
    ("dim_regions", "max_lat", "DOUBLE PRECISION"),
    ("dim_regions", "min_lon", "DOUBLE PRECISION"),
    ("dim_regions", "max_lon", "DOUBLE PRECISION"),
    ("dim_regions", "is_primary", "BOOLEAN DEFAULT FALSE"),
    ("dim_regions", "status", "VARCHAR(32)"),
    ("dim_regions", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ("dim_marine_zones", "zone_id", "VARCHAR(64)"),
    ("dim_marine_zones", "zone_key", "VARCHAR(64)"),
    ("dim_marine_zones", "country_id", "VARCHAR(8)"),
    ("dim_marine_zones", "region_id", "VARCHAR(64)"),
    ("dim_marine_zones", "status", "VARCHAR(32)"),
    ("dim_marine_zones", "notes", "TEXT"),
    ("dim_marine_zones", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ("dim_marine_zones", "min_lat", "DOUBLE PRECISION"),
    ("dim_marine_zones", "max_lat", "DOUBLE PRECISION"),
    ("dim_marine_zones", "min_lon", "DOUBLE PRECISION"),
    ("dim_marine_zones", "max_lon", "DOUBLE PRECISION"),
]

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_dim_regions_country ON dim_regions (country_id)",
    "CREATE INDEX IF NOT EXISTS idx_dim_ports_country ON dim_ports_ref (country_id)",
    "CREATE INDEX IF NOT EXISTS idx_dim_zones_region ON dim_marine_zones (region_id)",
]


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            text(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = :t
                """
            ),
            {"t": name},
        ).fetchone()
    )


def _columns(conn, name: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t
            """
        ),
        {"t": name},
    ).fetchall()
    return {r[0] for r in rows}


def _col_type(conn, table: str, col: str) -> str | None:
    row = conn.execute(
        text(
            """
            SELECT data_type FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :t AND column_name = :c
            """
        ),
        {"t": table, "c": col},
    ).fetchone()
    return row[0] if row else None


def ensure_schema(engine: Engine | None = None) -> None:
    eng = engine or _engine()
    reset = os.getenv("PHASE18_RESET", "").strip() in {"1", "true", "TRUE", "yes"}

    # Separate short transactions so one failure (legacy zone_key types, etc.)
    # cannot roll back CREATE TABLE for dim_countries / dim_ports_ref.
    if reset:
        with eng.begin() as conn:
            for t in ("dim_marine_zones", "dim_ports_ref", "dim_regions", "dim_countries"):
                conn.execute(text(f"DROP TABLE IF EXISTS {t} CASCADE"))
                logger.info("Dropped %s (PHASE18_RESET)", t)

    for ddl in DDL_STATEMENTS:
        try:
            with eng.begin() as conn:
                conn.execute(text(ddl))
        except Exception as e:
            logger.warning("DDL skipped/failed: %s — %s", ddl.split("(", 1)[0].strip()[:80], e)

    with eng.begin() as conn:
        for table, col, coltype in ALTER_COLUMNS:
            if not _table_exists(conn, table):
                continue
            if col in _columns(conn, table):
                continue
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {coltype}"))
                logger.info("Added %s.%s", table, col)
            except Exception as e:
                logger.warning("ADD COLUMN %s.%s skipped: %s", table, col, e)

    # Backfill zone_id from zone_key (legacy integer zone_key is fine via ::text)
    try:
        with eng.begin() as conn:
            if _table_exists(conn, "dim_marine_zones"):
                cols = _columns(conn, "dim_marine_zones")
                if "zone_id" in cols and "zone_key" in cols:
                    zk_type = (_col_type(conn, "dim_marine_zones", "zone_key") or "").lower()
                    if zk_type in {"integer", "bigint", "smallint", "numeric", "double precision", "real"}:
                        conn.execute(
                            text(
                                """
                                UPDATE dim_marine_zones
                                SET zone_id = zone_key::text
                                WHERE (zone_id IS NULL OR btrim(zone_id) = '')
                                  AND zone_key IS NOT NULL
                                """
                            )
                        )
                    else:
                        conn.execute(
                            text(
                                """
                                UPDATE dim_marine_zones
                                SET zone_id = zone_key::text
                                WHERE (zone_id IS NULL OR btrim(zone_id) = '')
                                  AND zone_key IS NOT NULL
                                  AND btrim(zone_key::text) <> ''
                                """
                            )
                        )
    except Exception as e:
        logger.warning("zone_id backfill skipped: %s", e)

    for idx in INDEXES:
        try:
            with eng.begin() as conn:
                conn.execute(text(idx))
        except Exception as e:
            logger.warning("Index skipped: %s", e)

    with eng.begin() as conn:
        for t in ("dim_countries", "dim_regions", "dim_ports_ref", "dim_marine_zones"):
            if _table_exists(conn, t):
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                logger.info("%s ready (%s rows)", t, n)
            else:
                logger.warning("%s missing after ensure", t)


def main() -> None:
    try:
        logger.info("Phase 18 init — regional hierarchy schema")
        ensure_schema()
        logger.info("Phase 18 init complete")
    except Exception as e:
        logger.exception("Phase 18 init failed: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
