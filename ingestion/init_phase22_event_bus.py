"""
Phase 22 — Event Bus schema.

Durable Postgres-backed bus (no Kafka). Idempotent DDL:
- keeps existing events
- adds primary keys / indexes when missing
- supports natural-key dedupe via source_key
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

from db_utils import pg_connection

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


DDL = [
    """
    CREATE TABLE IF NOT EXISTS pg.public.event_bus_topics (
        topic VARCHAR PRIMARY KEY,
        description VARCHAR,
        status VARCHAR DEFAULT 'ACTIVE'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pg.public.event_bus_consumers (
        consumer_id VARCHAR PRIMARY KEY,
        consumer_name VARCHAR,
        topics VARCHAR,
        status VARCHAR DEFAULT 'ACTIVE',
        last_seen_at TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pg.public.event_bus (
        event_id BIGINT PRIMARY KEY,
        topic VARCHAR NOT NULL,
        event_type VARCHAR NOT NULL,
        severity VARCHAR DEFAULT 'INFO',
        payload VARCHAR,
        region_id VARCHAR,
        country_id VARCHAR,
        source_table VARCHAR,
        source_key VARCHAR,
        status VARCHAR DEFAULT 'PENDING',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processed_at TIMESTAMP,
        model_version VARCHAR
    )
    """,
]


def _ensure_column(con, table: str, column: str, ddl_type: str) -> None:
    """Add a column if the table exists without it (best-effort migration)."""
    try:
        exists = con.execute(
            """
            SELECT 1
            FROM pg.information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = ?
              AND column_name = ?
            LIMIT 1
            """,
            [table, column],
        ).fetchone()
        if exists:
            return
        con.execute(f"ALTER TABLE pg.public.{table} ADD COLUMN {column} {ddl_type}")
        logger.info("Added column %s.%s", table, column)
    except Exception as exc:
        logger.warning("Could not ensure column %s.%s: %s", table, column, exc)


def _ensure_index(con, name: str, sql: str) -> None:
    try:
        con.execute(sql)
    except Exception as exc:
        # Index may already exist under another definition
        logger.debug("Index %s: %s", name, exc)


def main() -> None:
    logger.info("=== Phase 22 event bus schema ===")
    with pg_connection() as con:
        for stmt in DDL:
            con.execute(stmt)

        # Soft-migrate older installs that lacked source_key / PK
        _ensure_column(con, "event_bus", "source_key", "VARCHAR")
        _ensure_column(con, "event_bus", "processed_at", "TIMESTAMP")
        _ensure_column(con, "event_bus", "model_version", "VARCHAR")

        _ensure_index(
            con,
            "idx_event_bus_status_created",
            """
            CREATE INDEX IF NOT EXISTS idx_event_bus_status_created
            ON pg.public.event_bus (status, created_at DESC)
            """,
        )
        _ensure_index(
            con,
            "idx_event_bus_topic_created",
            """
            CREATE INDEX IF NOT EXISTS idx_event_bus_topic_created
            ON pg.public.event_bus (topic, created_at DESC)
            """,
        )
        _ensure_index(
            con,
            "idx_event_bus_source_key",
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_event_bus_source_key
            ON pg.public.event_bus (source_key)
            WHERE source_key IS NOT NULL
            """,
        )
        _ensure_index(
            con,
            "idx_event_bus_severity",
            """
            CREATE INDEX IF NOT EXISTS idx_event_bus_severity
            ON pg.public.event_bus (severity)
            """,
        )

    logger.info("=== Phase 22 schema ready ===")


if __name__ == "__main__":
    main()
