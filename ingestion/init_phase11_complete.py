"""Phase 11 complete schema: events, risks, freshness, provenance (Supabase)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

from db_utils import pg_connection  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("phase11-init")

TABLE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS public.data_freshness (
        source_key        VARCHAR PRIMARY KEY,
        source_name       VARCHAR,
        last_success_at   TIMESTAMPTZ,
        age_minutes       DOUBLE PRECISION,
        status            VARCHAR,
        expected_cadence  VARCHAR,
        notes             VARCHAR,
        updated_at        TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.spatial_intelligence (
        zone_id       VARCHAR NOT NULL,
        zone_name     VARCHAR,
        country_id    VARCHAR,
        risk_tier     VARCHAR,
        risk_score    DOUBLE PRECISION,
        vessel_count  INTEGER,
        dark_count    INTEGER,
        fishing_hours DOUBLE PRECISION,
        sst_c         DOUBLE PRECISION,
        bloom_risk    VARCHAR,
        notes         VARCHAR,
        as_of         DATE,
        computed_at   TIMESTAMPTZ,
        PRIMARY KEY (zone_id, as_of)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.oceanwatch_events (
        event_id      VARCHAR PRIMARY KEY,
        event_type    VARCHAR,
        severity      VARCHAR,
        title         VARCHAR,
        description   VARCHAR,
        lat           DOUBLE PRECISION,
        lon           DOUBLE PRECISION,
        region_id     VARCHAR,
        country_id    VARCHAR,
        risk_score    DOUBLE PRECISION,
        source        VARCHAR,
        status        VARCHAR,
        detected_at   TIMESTAMPTZ,
        created_at    TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.risk_scores (
        entity_type   VARCHAR NOT NULL,
        entity_id     VARCHAR NOT NULL,
        risk_score    DOUBLE PRECISION,
        risk_tier     VARCHAR,
        drivers       VARCHAR,
        as_of         DATE NOT NULL,
        computed_at   TIMESTAMPTZ,
        PRIMARY KEY (entity_type, entity_id, as_of)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.data_provenance (
        dataset_key      VARCHAR PRIMARY KEY,
        display_name     VARCHAR,
        provider         VARCHAR,
        license          VARCHAR,
        url              VARCHAR,
        refresh_cadence  VARCHAR,
        last_refresh     TIMESTAMPTZ,
        notes            VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.fact_wio_intelligence_index (
        index_date              DATE PRIMARY KEY,
        overall_score           DOUBLE PRECISION,
        maritime_score          DOUBLE PRECISION,
        ocean_score             DOUBLE PRECISION,
        fisheries_score         DOUBLE PRECISION,
        risk_score              DOUBLE PRECISION,
        confidence              DOUBLE PRECISION,
        drivers                 VARCHAR,
        region_id               VARCHAR,
        computed_at             TIMESTAMPTZ
    )
    """,
]

COLUMNS = {
    "data_freshness": [
        ("source_key", "VARCHAR"),
        ("source_name", "VARCHAR"),
        ("last_success_at", "TIMESTAMPTZ"),
        ("age_minutes", "DOUBLE PRECISION"),
        ("status", "VARCHAR"),
        ("expected_cadence", "VARCHAR"),
        ("notes", "VARCHAR"),
        ("updated_at", "TIMESTAMPTZ"),
    ],
    "spatial_intelligence": [
        ("zone_id", "VARCHAR"),
        ("zone_name", "VARCHAR"),
        ("country_id", "VARCHAR"),
        ("risk_tier", "VARCHAR"),
        ("risk_score", "DOUBLE PRECISION"),
        ("vessel_count", "INTEGER"),
        ("dark_count", "INTEGER"),
        ("fishing_hours", "DOUBLE PRECISION"),
        ("sst_c", "DOUBLE PRECISION"),
        ("bloom_risk", "VARCHAR"),
        ("notes", "VARCHAR"),
        ("as_of", "DATE"),
        ("computed_at", "TIMESTAMPTZ"),
    ],
    "oceanwatch_events": [
        ("event_id", "VARCHAR"),
        ("event_type", "VARCHAR"),
        ("severity", "VARCHAR"),
        ("title", "VARCHAR"),
        ("description", "VARCHAR"),
        ("lat", "DOUBLE PRECISION"),
        ("lon", "DOUBLE PRECISION"),
        ("region_id", "VARCHAR"),
        ("country_id", "VARCHAR"),
        ("risk_score", "DOUBLE PRECISION"),
        ("source", "VARCHAR"),
        ("status", "VARCHAR"),
        ("detected_at", "TIMESTAMPTZ"),
        ("created_at", "TIMESTAMPTZ"),
    ],
    "risk_scores": [
        ("entity_type", "VARCHAR"),
        ("entity_id", "VARCHAR"),
        ("risk_score", "DOUBLE PRECISION"),
        ("risk_tier", "VARCHAR"),
        ("drivers", "VARCHAR"),
        ("as_of", "DATE"),
        ("computed_at", "TIMESTAMPTZ"),
    ],
    "data_provenance": [
        ("dataset_key", "VARCHAR"),
        ("display_name", "VARCHAR"),
        ("provider", "VARCHAR"),
        ("license", "VARCHAR"),
        ("url", "VARCHAR"),
        ("refresh_cadence", "VARCHAR"),
        ("last_refresh", "TIMESTAMPTZ"),
        ("notes", "VARCHAR"),
    ],
    "fact_wio_intelligence_index": [
        ("index_date", "DATE"),
        ("overall_score", "DOUBLE PRECISION"),
        ("maritime_score", "DOUBLE PRECISION"),
        ("ocean_score", "DOUBLE PRECISION"),
        ("fisheries_score", "DOUBLE PRECISION"),
        ("risk_score", "DOUBLE PRECISION"),
        ("confidence", "DOUBLE PRECISION"),
        ("drivers", "VARCHAR"),
        ("region_id", "VARCHAR"),
        ("computed_at", "TIMESTAMPTZ"),
    ],
}


def _ensure_column(con, table: str, column: str, col_type: str) -> None:
    try:
        con.execute(
            f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        )
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass
        if "already" in msg or "duplicate" in msg:
            return
        try:
            cur = con.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema='public' AND table_name=%s AND column_name=%s
                LIMIT 1
                """,
                (table, column),
            )
            if cur.fetchone():
                return
            con.execute(f"ALTER TABLE public.{table} ADD COLUMN {column} {col_type}")
        except Exception:  # noqa: BLE001
            try:
                con.rollback()
            except Exception:  # noqa: BLE001
                pass
            logger.debug("column %s.%s: %s", table, column, exc)


def main() -> None:
    logger.info("=== Phase 11 schema ===")
    with pg_connection() as con:
        for stmt in TABLE_DDL:
            con.execute(stmt)
        for table, cols in COLUMNS.items():
            for col, typ in cols:
                _ensure_column(con, table, col, typ)
        for idx in [
            "CREATE INDEX IF NOT EXISTS idx_ow_events_detected ON public.oceanwatch_events (detected_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_spatial_as_of ON public.spatial_intelligence (as_of DESC)",
            "CREATE INDEX IF NOT EXISTS idx_risk_scores_as_of ON public.risk_scores (as_of DESC)",
        ]:
            try:
                con.execute(idx)
            except Exception as exc:  # noqa: BLE001
                logger.debug("index: %s", exc)
                try:
                    con.rollback()
                except Exception:  # noqa: BLE001
                    pass
    logger.info("=== Phase 11 schema ready ===")


if __name__ == "__main__":
    main()
