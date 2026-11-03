"""
Phase 22 — Event Bus schema.

Durable Postgres-backed bus (no Kafka). Idempotent DDL:
- CREATE TABLE IF NOT EXISTS
- ADD COLUMN IF NOT EXISTS for legacy installs
- primary keys / indexes when missing
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

from db_utils import pg_connection  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("phase22-init")

# Canonical contract used by publisher + Streamlit Event Bus page
TABLE_DDL = [
    """
    CREATE TABLE IF NOT EXISTS public.event_bus (
        event_id       VARCHAR PRIMARY KEY,
        topic          VARCHAR,
        event_type     VARCHAR,
        severity       VARCHAR,
        status         VARCHAR,
        title          VARCHAR,
        message        VARCHAR,
        payload        VARCHAR,
        region_id      VARCHAR,
        country_id     VARCHAR,
        source_table   VARCHAR,
        source_key     VARCHAR,
        created_at     TIMESTAMPTZ,
        published_at   TIMESTAMPTZ,
        processed_at   TIMESTAMPTZ,
        consumed_at    TIMESTAMPTZ,
        error_message  VARCHAR,
        model_version  VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.event_bus_topics (
        topic        VARCHAR PRIMARY KEY,
        description  VARCHAR,
        owner        VARCHAR,
        status       VARCHAR,
        created_at   TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.event_bus_consumers (
        consumer_id    VARCHAR PRIMARY KEY,
        consumer_name  VARCHAR,
        topics         VARCHAR,
        status         VARCHAR,
        last_seen_at   TIMESTAMPTZ
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS public.event_bus_offsets (
        consumer_id    VARCHAR NOT NULL,
        topic          VARCHAR NOT NULL,
        last_event_id  VARCHAR,
        updated_at     TIMESTAMPTZ,
        PRIMARY KEY (consumer_id, topic)
    )
    """,
]

# column migrations for legacy CREATE TABLE IF NOT EXISTS installs
COLUMNS: dict[str, list[tuple[str, str]]] = {
    "event_bus": [
        ("event_id", "VARCHAR"),
        ("topic", "VARCHAR"),
        ("event_type", "VARCHAR"),
        ("severity", "VARCHAR"),
        ("status", "VARCHAR"),
        ("title", "VARCHAR"),
        ("message", "VARCHAR"),
        ("payload", "VARCHAR"),
        ("region_id", "VARCHAR"),
        ("country_id", "VARCHAR"),
        ("source_table", "VARCHAR"),
        ("source_key", "VARCHAR"),
        ("created_at", "TIMESTAMPTZ"),
        ("published_at", "TIMESTAMPTZ"),
        ("processed_at", "TIMESTAMPTZ"),
        ("consumed_at", "TIMESTAMPTZ"),
        ("error_message", "VARCHAR"),
        ("model_version", "VARCHAR"),
    ],
    "event_bus_topics": [
        ("topic", "VARCHAR"),
        ("description", "VARCHAR"),
        ("owner", "VARCHAR"),
        ("status", "VARCHAR"),
        ("created_at", "TIMESTAMPTZ"),
    ],
    "event_bus_consumers": [
        ("consumer_id", "VARCHAR"),
        ("consumer_name", "VARCHAR"),
        ("topics", "VARCHAR"),
        ("status", "VARCHAR"),
        ("last_seen_at", "TIMESTAMPTZ"),
    ],
}

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_event_bus_topic_created ON public.event_bus (topic, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_event_bus_status ON public.event_bus (status)",
    "CREATE INDEX IF NOT EXISTS idx_event_bus_created ON public.event_bus (created_at DESC)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_event_bus_source ON public.event_bus (source_table, source_key)",
]


def _ensure_column(con, table: str, column: str, col_type: str) -> None:
    try:
        con.execute(
            f"ALTER TABLE public.{table} ADD COLUMN IF NOT EXISTS {column} {col_type}"
        )
        logger.info("column ok: %s.%s", table, column)
    except Exception as exc:  # noqa: BLE001
        # older PG without IF NOT EXISTS on ADD COLUMN
        msg = str(exc).lower()
        if "already exists" in msg or "duplicate" in msg:
            return
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass
        try:
            cur = con.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                  AND column_name = %s
                LIMIT 1
                """,
                (table, column),
            )
            if cur.fetchone():
                return
            con.execute(
                f"ALTER TABLE public.{table} ADD COLUMN {column} {col_type}"
            )
            logger.info("column added: %s.%s", table, column)
        except Exception as exc2:  # noqa: BLE001
            logger.debug("column %s.%s: %s / %s", table, column, exc, exc2)
            try:
                con.rollback()
            except Exception:  # noqa: BLE001
                pass


def _ensure_pk(con, table: str, column: str) -> None:
    try:
        con.execute(f"ALTER TABLE public.{table} ADD PRIMARY KEY ({column})")
        logger.info("pk added: %s(%s)", table, column)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if any(s in msg for s in ("already", "exists", "multiple primary")):
            logger.debug("pk exists: %s", table)
        else:
            logger.debug("pk %s: %s", table, exc)
        try:
            con.rollback()
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    logger.info("=== Phase 22 event bus schema ===")
    with pg_connection() as con:
        for stmt in TABLE_DDL:
            con.execute(stmt)
            logger.info("DDL ok")

        for table, col_list in COLUMNS.items():
            for col, typ in col_list:
                _ensure_column(con, table, col, typ)

        _ensure_pk(con, "event_bus", "event_id")
        _ensure_pk(con, "event_bus_topics", "topic")
        _ensure_pk(con, "event_bus_consumers", "consumer_id")

        for stmt in INDEX_DDL:
            try:
                con.execute(stmt)
            except Exception as exc:  # noqa: BLE001
                logger.debug("index: %s", exc)
                try:
                    con.rollback()
                except Exception:  # noqa: BLE001
                    pass

    logger.info("=== Phase 22 event bus schema ready ===")


if __name__ == "__main__":
    main()
