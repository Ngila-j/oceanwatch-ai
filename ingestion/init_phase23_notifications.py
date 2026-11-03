"""
Phase 23 — notification / delivery engine schema.

Idempotent DDL (does not drop existing queue/delivery history).
SQLAlchemy / Supabase-safe (no DuckDB pg.public path required).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _load_env() -> None:
    env_path = _INGESTION_DIR / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        import os

        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def get_db_uri() -> str:
    import os

    _load_env()
    try:
        from db_utils import get_db_uri as _g

        uri = _g()
    except Exception:  # noqa: BLE001
        uri = os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or ""
    if not uri:
        raise RuntimeError("OCEANWATCH_DB_URI / DATABASE_URL not set")
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


def _engine():
    uri = get_db_uri()
    args = {"connect_timeout": 20, "options": "-c statement_timeout=60000"}
    if "supabase" in uri.lower() or "pooler" in uri.lower():
        args["sslmode"] = "require"
    return create_engine(uri, pool_pre_ping=True, connect_args=args, pool_size=1, max_overflow=0)


DDL = [
    """
    CREATE TABLE IF NOT EXISTS dim_notification_channels (
        channel_id VARCHAR PRIMARY KEY,
        channel_name VARCHAR,
        channel_type VARCHAR,
        status VARCHAR DEFAULT 'DRY_RUN',
        notes VARCHAR
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS dim_notification_templates (
        template_id VARCHAR PRIMARY KEY,
        topic VARCHAR,
        severity_min VARCHAR,
        subject_template VARCHAR,
        body_template VARCHAR,
        status VARCHAR DEFAULT 'ACTIVE'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fact_notification_queue (
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
    CREATE TABLE IF NOT EXISTS fact_notification_deliveries (
        delivery_id BIGINT PRIMARY KEY,
        queue_id BIGINT,
        event_id BIGINT,
        channel_id VARCHAR,
        recipient VARCHAR,
        delivery_status VARCHAR,
        response_code VARCHAR,
        response_message VARCHAR,
        delivered_at TIMESTAMP,
        model_version VARCHAR
    )
    """,
]

INDEXES = [
    """
    CREATE INDEX IF NOT EXISTS idx_notif_queue_event
    ON fact_notification_queue (event_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_notif_queue_created
    ON fact_notification_queue (created_at DESC)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_notif_deliv_event
    ON fact_notification_deliveries (event_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_notif_deliv_delivered
    ON fact_notification_deliveries (delivered_at DESC)
    """,
]

# Minimal seed so the console is not empty before first run
CHANNELS = [
    ("log", "Delivery log (dry-run)", "INTERNAL", "ACTIVE", "Always-on local outbox / log channel."),
    ("email", "Email (simulated)", "EMAIL", "DRY_RUN", "No live SMTP until credentials configured."),
    ("whatsapp", "WhatsApp (stretch)", "WHATSAPP", "DRY_RUN", "Stretch goal — dry-run only."),
]


def main() -> None:
    logger.info("=== Phase 23 notifications schema ===")
    eng = _engine()
    with eng.begin() as conn:
        for stmt in DDL:
            conn.execute(text(stmt))
        for stmt in INDEXES:
            try:
                conn.execute(text(stmt))
            except Exception as exc:  # noqa: BLE001
                logger.debug("index: %s", exc)

        # Upsert default channels
        for channel_id, name, ctype, status, notes in CHANNELS:
            conn.execute(
                text(
                    """
                    INSERT INTO dim_notification_channels
                        (channel_id, channel_name, channel_type, status, notes)
                    VALUES (:id, :name, :ctype, :status, :notes)
                    ON CONFLICT (channel_id) DO UPDATE SET
                        channel_name = EXCLUDED.channel_name,
                        channel_type = EXCLUDED.channel_type,
                        status = EXCLUDED.status,
                        notes = EXCLUDED.notes
                    """
                ),
                {
                    "id": channel_id,
                    "name": name,
                    "ctype": ctype,
                    "status": status,
                    "notes": notes,
                },
            )

        n_ch = conn.execute(text("SELECT COUNT(*) FROM dim_notification_channels")).scalar()
        n_q = conn.execute(text("SELECT COUNT(*) FROM fact_notification_queue")).scalar()
        n_d = conn.execute(text("SELECT COUNT(*) FROM fact_notification_deliveries")).scalar()
        logger.info(
            "channels=%s queue=%s deliveries=%s",
            n_ch,
            n_q,
            n_d,
        )
    eng.dispose()
    logger.info("=== Phase 23 schema ready ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        logger.exception("init_phase23_notifications failed: %s", e)
        sys.exit(1)
