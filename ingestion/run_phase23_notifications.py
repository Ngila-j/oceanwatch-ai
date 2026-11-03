"""
Phase 23 — Alert Delivery & Notification Engine.

Consumes PENDING rows from event_bus, builds queue items, dry-run delivers,
and marks events PROCESSED. No real email/WhatsApp/SMS send in free/local mode.

SQLAlchemy / Supabase-safe.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import create_engine, text

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase23_notify_v1.1"
NOTIFY_TOPICS = {
    "ops.alerts",
    "fisheries.alerts",
    "risk.unified",
    "maritime.events",
    "ocean.state",
}


def _load_env() -> None:
    env_path = _INGESTION_DIR / ".env"
    if not env_path.exists():
        return
    import os

    for line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
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
    args = {"connect_timeout": 20, "options": "-c statement_timeout=120000"}
    if "supabase" in uri.lower() or "pooler" in uri.lower():
        args["sslmode"] = "require"
    return create_engine(uri, pool_pre_ping=True, connect_args=args, pool_size=1, max_overflow=0)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stable_id(*parts: Any) -> int:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:15], 16)


def severity_rank(s: Any) -> int:
    order = {
        "INFO": 0,
        "LOW": 1,
        "WATCH": 2,
        "ELEVATED": 3,
        "WARNING": 3,
        "HIGH": 4,
        "ALERT": 4,
        "CRITICAL": 5,
        "SEVERE": 5,
    }
    return order.get(str(s or "INFO").upper(), 0)


CHANNELS = [
    dict(
        channel_id="log",
        channel_name="Delivery log (dry-run)",
        channel_type="INTERNAL",
        status="ACTIVE",
        notes="Always-on local outbox / log channel.",
    ),
    dict(
        channel_id="email",
        channel_name="Email (simulated)",
        channel_type="EMAIL",
        status="DRY_RUN",
        notes="No live SMTP until credentials configured.",
    ),
    dict(
        channel_id="whatsapp",
        channel_name="WhatsApp (stretch)",
        channel_type="WHATSAPP",
        status="DRY_RUN",
        notes="Stretch goal — dry-run only.",
    ),
]

TEMPLATES = [
    dict(
        template_id="tpl_ops",
        topic="ops.alerts",
        severity_min="WATCH",
        subject_template="[OceanWatch Ops] {event_type} ({severity})",
        body_template="Ops alert {event_type} severity={severity} topic={topic}. Dry-run delivery only.",
        status="ACTIVE",
    ),
    dict(
        template_id="tpl_fisheries",
        topic="fisheries.alerts",
        severity_min="WATCH",
        subject_template="[OceanWatch Fisheries] {event_type}",
        body_template="Fisheries heuristic alert {event_type}. Not a legal determination.",
        status="ACTIVE",
    ),
    dict(
        template_id="tpl_risk",
        topic="risk.unified",
        severity_min="WATCH",
        subject_template="[OceanWatch Risk] Composite {severity}",
        body_template="Unified risk event {event_type} severity={severity}. Decision-support only.",
        status="ACTIVE",
    ),
    dict(
        template_id="tpl_maritime",
        topic="maritime.events",
        severity_min="WATCH",
        subject_template="[OceanWatch Maritime] {event_type}",
        body_template="Maritime event {event_type} on {topic}. Severity={severity}.",
        status="ACTIVE",
    ),
    dict(
        template_id="tpl_ocean",
        topic="ocean.state",
        severity_min="WATCH",
        subject_template="[OceanWatch Ocean] {event_type}",
        body_template="Ocean state notice {event_type} severity={severity}.",
        status="ACTIVE",
    ),
]


def _render(tpl: Any, **kwargs: Any) -> str:
    try:
        return str(tpl or "").format(**kwargs)
    except Exception:
        return str(tpl or "")


def _ensure_schema(conn) -> None:
    """Create notification tables if missing (idempotent)."""
    for stmt in (
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
    ):
        conn.execute(text(stmt))


def _existing_ids(conn, table: str, id_col: str, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    found: set[int] = set()
    chunk = 400
    for i in range(0, len(ids), chunk):
        part = [int(x) for x in ids[i : i + chunk]]
        ph = ", ".join(f":id{j}" for j in range(len(part)))
        params = {f"id{j}": v for j, v in enumerate(part)}
        rows = conn.execute(
            text(f"SELECT {id_col} AS id FROM {table} WHERE {id_col} IN ({ph})"),
            params,
        ).fetchall()
        for r in rows:
            found.add(int(r[0]))
    return found


def _upsert_dims(conn) -> None:
    for ch in CHANNELS:
        conn.execute(
            text(
                """
                INSERT INTO dim_notification_channels
                    (channel_id, channel_name, channel_type, status, notes)
                VALUES (:channel_id, :channel_name, :channel_type, :status, :notes)
                ON CONFLICT (channel_id) DO UPDATE SET
                    channel_name = EXCLUDED.channel_name,
                    channel_type = EXCLUDED.channel_type,
                    status = EXCLUDED.status,
                    notes = EXCLUDED.notes
                """
            ),
            ch,
        )
    for tpl in TEMPLATES:
        conn.execute(
            text(
                """
                INSERT INTO dim_notification_templates
                    (template_id, topic, severity_min, subject_template, body_template, status)
                VALUES
                    (:template_id, :topic, :severity_min, :subject_template, :body_template, :status)
                ON CONFLICT (template_id) DO UPDATE SET
                    topic = EXCLUDED.topic,
                    severity_min = EXCLUDED.severity_min,
                    subject_template = EXCLUDED.subject_template,
                    body_template = EXCLUDED.body_template,
                    status = EXCLUDED.status
                """
            ),
            tpl,
        )


def _insert_rows(conn, table: str, rows: list[dict], cols: list[str]) -> int:
    if not rows:
        return 0
    col_list = ", ".join(cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    sql = text(f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) ON CONFLICT DO NOTHING")
    n = 0
    for row in rows:
        conn.execute(sql, {c: row.get(c) for c in cols})
        n += 1
    return n


def run() -> None:
    logger.info("=== Phase 23 Notification Engine ===")
    now = _utcnow()
    recipients = ["ops@oceanwatch.local", "watchdesk@oceanwatch.local"]

    eng = _engine()
    with eng.begin() as conn:
        _ensure_schema(conn)
        _upsert_dims(conn)

        templates_df = pd.read_sql(
            text("SELECT * FROM dim_notification_templates WHERE UPPER(COALESCE(status,'ACTIVE')) = 'ACTIVE'"),
            conn,
        )
        tpl_by_topic = {str(r["topic"]): r for _, r in templates_df.iterrows()} if not templates_df.empty else {}

        # Prefer topic-filtered pending events; fall back to any pending if bus is sparse
        events = pd.read_sql(
            text(
                """
                SELECT
                    event_id, topic, event_type, severity, status, payload, created_at
                FROM event_bus
                WHERE UPPER(COALESCE(status, 'PENDING')) = 'PENDING'
                ORDER BY created_at ASC NULLS LAST
                LIMIT 500
                """
            ),
            conn,
        )

        if events.empty:
            logger.info("No PENDING events on event_bus")
        else:
            logger.info("Found %s PENDING event(s)", len(events))

        queue_rows: list[dict] = []
        delivery_rows: list[dict] = []
        processed_ids: list[int] = []

        for _, ev in events.iterrows():
            topic = str(ev.get("topic") or "").strip()
            severity = str(ev.get("severity") or "INFO").upper()
            event_type = str(ev.get("event_type") or "EVENT")
            try:
                event_id = int(ev.get("event_id"))
            except Exception:
                continue

            # Only fan-out known notify topics; still process others with log-only
            tpl = tpl_by_topic.get(topic)
            if tpl is None:
                # Generic fallback template for any pending event
                tpl = {
                    "subject_template": "[OceanWatch] {event_type} ({severity})",
                    "body_template": "Event {event_type} on topic {topic}. Severity={severity}. Dry-run only.",
                    "severity_min": "INFO",
                }

            if severity_rank(severity) < severity_rank(tpl.get("severity_min") or "WATCH"):
                processed_ids.append(event_id)
                continue

            subject = _render(
                tpl.get("subject_template"),
                event_type=event_type,
                severity=severity,
                topic=topic,
            )
            body = _render(
                tpl.get("body_template"),
                event_type=event_type,
                severity=severity,
                topic=topic,
            )

            channel_list = ["log"]
            if severity_rank(severity) >= severity_rank("WATCH"):
                channel_list.extend(["email", "whatsapp"])

            for channel_id in channel_list:
                rec_list = ["system"] if channel_id == "log" else recipients
                for recipient in rec_list:
                    qid = _stable_id("q", event_id, channel_id, recipient, MODEL)
                    did = _stable_id("d", qid, channel_id, recipient, MODEL)
                    queue_rows.append(
                        dict(
                            queue_id=qid,
                            event_id=event_id,
                            topic=topic,
                            event_type=event_type,
                            severity=severity,
                            channel_id=channel_id,
                            recipient=recipient,
                            subject=subject,
                            body=body,
                            status="QUEUED" if channel_id != "log" else "LOGGED",
                            created_at=now,
                            model_version=MODEL,
                        )
                    )
                    delivery_rows.append(
                        dict(
                            delivery_id=did,
                            queue_id=qid,
                            event_id=event_id,
                            channel_id=channel_id,
                            recipient=recipient,
                            delivery_status="LOGGED" if channel_id == "log" else "DRY_RUN_OK",
                            response_code="200",
                            response_message="dry-run simulated",
                            delivered_at=now,
                            model_version=MODEL,
                        )
                    )

            processed_ids.append(event_id)

        # Append-only writes with id-level dedupe
        if queue_rows:
            qdf_new = pd.DataFrame(queue_rows)
            have_q = _existing_ids(
                conn,
                "fact_notification_queue",
                "queue_id",
                [int(x) for x in qdf_new["queue_id"].tolist()],
            )
            fresh_q = qdf_new[~qdf_new["queue_id"].astype(int).isin(have_q)]
            n_q = _insert_rows(
                conn,
                "fact_notification_queue",
                fresh_q.to_dict(orient="records"),
                [
                    "queue_id",
                    "event_id",
                    "topic",
                    "event_type",
                    "severity",
                    "channel_id",
                    "recipient",
                    "subject",
                    "body",
                    "status",
                    "created_at",
                    "model_version",
                ],
            )
            logger.info("Queued %s new notification(s) (skipped %s existing)", n_q, len(qdf_new) - n_q)

        if delivery_rows:
            ddf_new = pd.DataFrame(delivery_rows)
            have_d = _existing_ids(
                conn,
                "fact_notification_deliveries",
                "delivery_id",
                [int(x) for x in ddf_new["delivery_id"].tolist()],
            )
            fresh_d = ddf_new[~ddf_new["delivery_id"].astype(int).isin(have_d)]
            n_d = _insert_rows(
                conn,
                "fact_notification_deliveries",
                fresh_d.to_dict(orient="records"),
                [
                    "delivery_id",
                    "queue_id",
                    "event_id",
                    "channel_id",
                    "recipient",
                    "delivery_status",
                    "response_code",
                    "response_message",
                    "delivered_at",
                    "model_version",
                ],
            )
            logger.info("Recorded %s delivery row(s) (skipped %s existing)", n_d, len(ddf_new) - n_d)

        # Mark events processed (if event_bus exists)
        marked = 0
        for eid in sorted(set(processed_ids)):
            try:
                res = conn.execute(
                    text(
                        """
                        UPDATE event_bus
                        SET status = 'PROCESSED', processed_at = :ts
                        WHERE event_id = :eid
                          AND UPPER(COALESCE(status, 'PENDING')) = 'PENDING'
                        """
                    ),
                    {"ts": now, "eid": eid},
                )
                marked += res.rowcount or 0
            except Exception as exc:  # noqa: BLE001
                logger.debug("mark processed %s: %s", eid, exc)
        logger.info("Marked %s event(s) PROCESSED", marked)

        try:
            pending_left = conn.execute(
                text(
                    """
                    SELECT COUNT(*) FROM event_bus
                    WHERE UPPER(COALESCE(status, 'PENDING')) = 'PENDING'
                    """
                )
            ).scalar()
            logger.info("PENDING remaining on bus: %s", pending_left)
        except Exception:  # noqa: BLE001
            pass

        n_ch = conn.execute(text("SELECT COUNT(*) FROM dim_notification_channels")).scalar()
        n_tpl = conn.execute(text("SELECT COUNT(*) FROM dim_notification_templates")).scalar()
        n_queue = conn.execute(text("SELECT COUNT(*) FROM fact_notification_queue")).scalar()
        n_del = conn.execute(text("SELECT COUNT(*) FROM fact_notification_deliveries")).scalar()
        logger.info(
            "totals channels=%s templates=%s queue=%s deliveries=%s",
            n_ch,
            n_tpl,
            n_queue,
            n_del,
        )

    eng.dispose()
    logger.info("=== Phase 23 complete ===")


if __name__ == "__main__":
    try:
        run()
    except Exception as e:  # noqa: BLE001
        logger.exception("run_phase23_notifications failed: %s", e)
        sys.exit(1)
