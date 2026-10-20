"""
Phase 23 — notification / delivery engine schema.

Idempotent DDL (does not drop existing queue/delivery history).
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
    CREATE TABLE IF NOT EXISTS pg.public.dim_notification_channels (
        channel_id VARCHAR PRIMARY KEY,
        channel_name VARCHAR,
        channel_type VARCHAR,
        status VARCHAR DEFAULT 'DRY_RUN',
        notes VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pg.public.dim_notification_templates (
        template_id VARCHAR PRIMARY KEY,
        topic VARCHAR,
        severity_min VARCHAR,
        subject_template VARCHAR,
        body_template VARCHAR,
        status VARCHAR DEFAULT 'ACTIVE'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pg.public.fact_notification_queue (
        queue_id BIGINT PRIMARY KEY,
        event_id BIGINT,
        topic VARCHAR,
        event_type VARCHAR,
        severity VARCHAR,
        channel_id VARCHAR,
        recipient VARCHAR,
        subject VARCHAR,
        body VARCHAR,
        status VARCHAR,
        created_at TIMESTAMP,
        model_version VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pg.public.fact_notification_deliveries (
        delivery_id BIGINT PRIMARY KEY,
        queue_id BIGINT,
        event_id BIGINT,
        channel_id VARCHAR,
        recipient VARCHAR,
        delivery_status VARCHAR,
        attempt INTEGER,
        response_code VARCHAR,
        response_message VARCHAR,
        delivered_at TIMESTAMP,
        model_version VARCHAR
    )
    """,
]


def _ensure_index(con, sql: str) -> None:
    try:
        con.execute(sql)
    except Exception as exc:
        logger.debug("index: %s", exc)


def main() -> None:
    logger.info("=== Phase 23 notifications schema ===")
    with pg_connection() as con:
        for stmt in DDL:
            con.execute(stmt)

        _ensure_index(
            con,
            """
            CREATE INDEX IF NOT EXISTS idx_notif_queue_event
            ON pg.public.fact_notification_queue (event_id)
            """,
        )
        _ensure_index(
            con,
            """
            CREATE INDEX IF NOT EXISTS idx_notif_queue_status
            ON pg.public.fact_notification_queue (status, created_at DESC)
            """,
        )
        _ensure_index(
            con,
            """
            CREATE INDEX IF NOT EXISTS idx_notif_deliveries_event
            ON pg.public.fact_notification_deliveries (event_id, delivered_at DESC)
            """,
        )
    logger.info("=== Phase 23 schema ready ===")


if __name__ == "__main__":
    main()
