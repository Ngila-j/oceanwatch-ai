"""
Phase 23 — Alert Delivery & Notification Engine.

Consumes PENDING rows from event_bus, builds queue items, dry-run delivers,
and marks events PROCESSED. No real email/WhatsApp/SMS send in free/local mode.

Design fixes:
- Shared db_utils (URI, connection lifecycle, writes)
- Stable queue/delivery ids (no random collisions)
- Does not wipe historical queue/deliveries each run (append + skip duplicates)
- Explicit column projections from event_bus
"""

from __future__ import annotations

import hashlib
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

from db_utils import pg_connection, qdf, write_frame

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
    }
    return order.get(str(s or "INFO").upper(), 0)


CHANNELS = [
    dict(
        channel_id="log",
        channel_name="Delivery log (dry-run)",
        channel_type="INTERNAL",
        status="ACTIVE",
        notes="Always on — records delivery without external API calls.",
    ),
    dict(
        channel_id="email",
        channel_name="Email (dry-run)",
        channel_type="EMAIL",
        status="DRY_RUN",
        notes="Simulated SMTP until credentials configured.",
    ),
    dict(
        channel_id="whatsapp",
        channel_name="WhatsApp (dry-run)",
        channel_type="WHATSAPP",
        status="DRY_RUN",
        notes="Simulated WhatsApp Business API.",
    ),
]

TEMPLATES = [
    dict(
        template_id="tpl_ops",
        topic="ops.alerts",
        severity_min="WATCH",
        subject_template="[OceanWatch Ops] {event_type} ({severity})",
        body_template="Operational alert {event_type} at severity {severity}. Decision-support only.",
        status="ACTIVE",
    ),
    dict(
        template_id="tpl_risk",
        topic="risk.unified",
        severity_min="WATCH",
        subject_template="[OceanWatch Risk] Composite {severity}",
        body_template="Unified risk update: {event_type} · severity {severity}.",
        status="ACTIVE",
    ),
    dict(
        template_id="tpl_ocean",
        topic="ocean.state",
        severity_min="WATCH",
        subject_template="[OceanWatch Ocean] {event_type}",
        body_template="Ocean state event {event_type} ({severity}).",
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
        template_id="tpl_maritime",
        topic="maritime.events",
        severity_min="HIGH",
        subject_template="[OceanWatch Maritime] {event_type}",
        body_template="Maritime event {event_type} ({severity}).",
        status="ACTIVE",
    ),
]


def _render(tpl: str, **kwargs) -> str:
    try:
        return str(tpl or "").format(**kwargs)
    except Exception:
        return str(tpl or "")


def _existing_ids(con, table: str, id_col: str, ids: list[int]) -> set[int]:
    if not ids:
        return set()
    found: set[int] = set()
    chunk = 400
    for i in range(0, len(ids), chunk):
        part = ids[i : i + chunk]
        ph = ", ".join(["?"] * len(part))
        df = qdf(
            con,
            f"SELECT {id_col} AS id FROM pg.public.{table} WHERE {id_col} IN ({ph})",
            part,
        )
        if not df.empty:
            found.update(int(x) for x in df["id"].dropna().tolist())
    return found


def run() -> None:
    logger.info("=== Phase 23 Notification Engine ===")
    now = _utcnow()
    recipients = ["ops@oceanwatch.local", "watchdesk@oceanwatch.local"]

    with pg_connection() as con:
        write_frame(con, "dim_notification_channels", pd.DataFrame(CHANNELS), replace=True)
        write_frame(con, "dim_notification_templates", pd.DataFrame(TEMPLATES), replace=True)

        templates = pd.DataFrame(TEMPLATES)
        tpl_by_topic = {r["topic"]: r for _, r in templates.iterrows()}

        events = qdf(
            con,
            """
            SELECT
                event_id, topic, event_type, severity, status,
                region_id, source_table, source_key, created_at, payload
            FROM pg.public.event_bus
            WHERE UPPER(COALESCE(status, 'PENDING')) = 'PENDING'
            ORDER BY created_at ASC
            LIMIT 500
            """,
        )
        logger.info("Pending bus events: %s", len(events))

        queue_rows: list[dict] = []
        delivery_rows: list[dict] = []
        processed_ids: list[int] = []

        for _, ev in events.iterrows():
            topic = str(ev.get("topic") or "")
            if topic not in NOTIFY_TOPICS:
                # Still mark non-notify topics processed so they do not clog PENDING forever
                try:
                    processed_ids.append(int(ev.get("event_id")))
                except Exception:
                    pass
                continue

            severity = str(ev.get("severity") or "INFO").upper()
            event_type = str(ev.get("event_type") or "EVENT")
            try:
                event_id = int(ev.get("event_id"))
            except Exception:
                continue

            tpl = tpl_by_topic.get(topic)
            if tpl is None:
                processed_ids.append(event_id)
                continue

            if severity_rank(severity) < severity_rank(tpl.get("severity_min") or "WATCH"):
                # Below threshold: acknowledge without fan-out
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
                    qid = _stable_id("q", event_id, channel_id, recipient)
                    did = _stable_id("d", qid, channel_id, recipient)
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
                            attempt=1,
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
            have_q = _existing_ids(con, "fact_notification_queue", "queue_id", qdf_new["queue_id"].tolist())
            qdf_new = qdf_new[~qdf_new["queue_id"].isin(have_q)]
            write_frame(con, "fact_notification_queue", qdf_new, replace=False)

        if delivery_rows:
            ddf_new = pd.DataFrame(delivery_rows)
            have_d = _existing_ids(
                con, "fact_notification_deliveries", "delivery_id", ddf_new["delivery_id"].tolist()
            )
            ddf_new = ddf_new[~ddf_new["delivery_id"].isin(have_d)]
            write_frame(con, "fact_notification_deliveries", ddf_new, replace=False)

        # Mark bus events processed
        marked = 0
        for eid in sorted(set(processed_ids)):
            try:
                con.execute(
                    """
                    UPDATE pg.public.event_bus
                    SET status = 'PROCESSED', processed_at = ?
                    WHERE event_id = ?
                      AND UPPER(COALESCE(status, 'PENDING')) = 'PENDING'
                    """,
                    [now, eid],
                )
                marked += 1
            except Exception as exc:
                logger.warning("Could not mark processed %s: %s", eid, exc)

        pending_left = qdf(
            con,
            "SELECT COUNT(*) AS n FROM pg.public.event_bus WHERE UPPER(COALESCE(status,'PENDING'))='PENDING'",
        )
        left = int(pending_left.iloc[0]["n"]) if not pending_left.empty else -1
        logger.info(
            "Queue+%s deliveries+%s marked_processed=%s pending_left=%s",
            len(queue_rows),
            len(delivery_rows),
            marked,
            left,
        )

    logger.info("=== Phase 23 complete ===")


if __name__ == "__main__":
    run()
