"""
Phase 23 complete — Alert Delivery & Notification Engine.
Consumes PENDING rows from event_bus, builds queue items, dry-run delivers,
marks events PROCESSED. No real email/WhatsApp/SMS send in free/local mode.
"""

import logging
import random
from datetime import datetime

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase23_notify_v1.0"

# Which severities trigger outbound notifications
NOTIFY_SEVERITIES = {"WATCH", "HIGH", "CRITICAL", "ELEVATED", "WARNING", "ALERT"}


def get_db_uri():
    import os

    if os.path.exists("/.dockerenv") or os.getenv("AIRFLOW_HOME"):
        return "postgresql://postgres:password@postgres:5432/oceanwatch_db"
    return "postgresql://postgres:password@localhost:5433/oceanwatch_db"


def connect():
    con = duckdb.connect()
    con.execute(f"ATTACH '{get_db_uri()}' AS pg (TYPE POSTGRES)")
    return con


def cols(con, table):
    try:
        return [
            r[0]
            for r in con.execute(
                """
                SELECT column_name FROM pg.information_schema.columns
                WHERE table_schema = 'public' AND table_name = ?
                """,
                [table],
            ).fetchall()
        ]
    except Exception:
        return []


def write(con, table, df, replace=True):
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return
    use = [c for c in df.columns if c in cols(con, table)]
    if not use:
        logger.warning("No columns for %s", table)
        return
    if replace:
        con.execute(f"DELETE FROM pg.public.{table}")
    con.register("_t", df[use])
    con.execute(
        f"INSERT INTO pg.public.{table} ({', '.join(use)}) SELECT {', '.join(use)} FROM _t"
    )
    logger.info("%s: %s rows", table, len(df))


def qdf(con, sql):
    try:
        return con.execute(sql).fetchdf()
    except Exception as e:
        logger.warning("Query failed: %s", e)
        return pd.DataFrame()


def severity_rank(s):
    order = {
        "INFO": 0,
        "LOW": 1,
        "WATCH": 2,
        "ELEVATED": 3,
        "WARNING": 3,
        "HIGH": 4,
        "CRITICAL": 5,
        "ALERT": 4,
    }
    return order.get(str(s or "INFO").upper(), 0)


def run():
    logger.info("=== Phase 23 Notification Engine ===")
    now = datetime.utcnow()
    con = connect()

    channels = pd.DataFrame(
        [
            dict(
                channel_id="log",
                channel_name="Delivery log (dry-run)",
                channel_type="INTERNAL",
                status="ACTIVE",
                notes="Always on — records delivery without external API",
            ),
            dict(
                channel_id="email",
                channel_name="Email",
                channel_type="EMAIL",
                status="DRY_RUN",
                notes="Wire SMTP later; currently simulated",
            ),
            dict(
                channel_id="whatsapp",
                channel_name="WhatsApp",
                channel_type="WHATSAPP",
                status="DRY_RUN",
                notes="Wire provider later; currently simulated",
            ),
            dict(
                channel_id="webhook",
                channel_name="Partner webhook",
                channel_type="WEBHOOK",
                status="PLANNED",
                notes="For API partners",
            ),
        ]
    )
    write(con, "dim_notification_channels", channels)

    templates = pd.DataFrame(
        [
            dict(
                template_id="tpl_ops",
                topic="ops.alerts",
                severity_min="WATCH",
                subject_template="[OceanWatch] {severity}: {event_type}",
                body_template="Operational alert {event_type} ({severity}). Region {region_id}. Event {event_id}.",
                status="ACTIVE",
            ),
            dict(
                template_id="tpl_maritime",
                topic="maritime.events",
                severity_min="WATCH",
                subject_template="[OceanWatch Maritime] {event_type}",
                body_template="Maritime event {event_type} severity {severity}. Review in Event Bus / Maritime Events.",
                status="ACTIVE",
            ),
            dict(
                template_id="tpl_risk",
                topic="risk.unified",
                severity_min="WATCH",
                subject_template="[OceanWatch Risk] Composite {severity}",
                body_template="Unified risk update severity {severity}. Open Unified Risk page for drivers.",
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
                template_id="tpl_fish",
                topic="fisheries.alerts",
                severity_min="WATCH",
                subject_template="[OceanWatch Fisheries] {event_type}",
                body_template="Fisheries heuristic alert {event_type}. Not a legal determination.",
                status="ACTIVE",
            ),
            dict(
                template_id="tpl_health",
                topic="system.health",
                severity_min="HIGH",
                subject_template="[OceanWatch System] {event_type}",
                body_template="Platform health signal {event_type}.",
                status="ACTIVE",
            ),
        ]
    )
    write(con, "dim_notification_templates", templates)

    # Prefer subscriptions if table exists
    subs = qdf(
        con,
        """
        SELECT * FROM pg.public.alert_subscriptions
        WHERE UPPER(COALESCE(status, 'ACTIVE')) IN ('ACTIVE', 'ENABLED', 'ON')
        """
    )
    recipients = []
    if not subs.empty:
        for _, s in subs.iterrows():
            email = s.get("email") or s.get("recipient") or s.get("contact")
            if email:
                recipients.append(str(email))
    if not recipients:
        recipients = ["ops@oceanwatch.local", "watchdesk@oceanwatch.local"]

    events = qdf(
        con,
        """
        SELECT * FROM pg.public.event_bus
        WHERE UPPER(COALESCE(status, 'PENDING')) = 'PENDING'
        ORDER BY created_at DESC
        LIMIT 500
        """
    )
    logger.info("Pending bus events: %s", len(events))

    tpl_by_topic = {r["topic"]: r for _, r in templates.iterrows()}
    queue_rows = []
    delivery_rows = []
    processed_ids = []

    for _, ev in events.iterrows():
        topic = str(ev.get("topic") or "")
        severity = str(ev.get("severity") or "INFO").upper()
        event_type = str(ev.get("event_type") or "EVENT")
        event_id = int(ev.get("event_id") or random.randint(10_000_000, 99_999_999))
        region_id = str(ev.get("region_id") or "kenya_eez")

        tpl = tpl_by_topic.get(topic)
        if tpl is None:
            continue
        if severity_rank(severity) < severity_rank(tpl.get("severity_min")):
            # Still mark processed so bus does not grow forever for INFO-only
            processed_ids.append(event_id)
            continue

        subject = (
            str(tpl["subject_template"])
            .replace("{severity}", severity)
            .replace("{event_type}", event_type)
            .replace("{event_id}", str(event_id))
            .replace("{region_id}", region_id)
        )
        body = (
            str(tpl["body_template"])
            .replace("{severity}", severity)
            .replace("{event_type}", event_type)
            .replace("{event_id}", str(event_id))
            .replace("{region_id}", region_id)
        )

        # Primary channels: log always; email/whatsapp dry-run for elevated+
        channel_list = ["log"]
        if severity_rank(severity) >= severity_rank("WATCH"):
            channel_list.extend(["email", "whatsapp"])

        for channel_id in channel_list:
            for recipient in recipients if channel_id != "log" else ["system"]:
                qid = random.randint(10_000_000, 99_999_999)
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
                        status="QUEUED",
                        created_at=now,
                        model_version=MODEL,
                    )
                )
                # Dry-run delivery
                delivery_rows.append(
                    dict(
                        delivery_id=random.randint(10_000_000, 99_999_999),
                        queue_id=qid,
                        event_id=event_id,
                        channel_id=channel_id,
                        recipient=recipient,
                        delivery_status="DRY_RUN_OK" if channel_id != "log" else "LOGGED",
                        attempt=1,
                        response_code="200",
                        response_message=f"Simulated {channel_id} delivery (Phase 23 dry-run)",
                        delivered_at=now,
                        model_version=MODEL,
                    )
                )
        processed_ids.append(event_id)

    write(con, "fact_notification_queue", pd.DataFrame(queue_rows))
    write(con, "fact_notification_deliveries", pd.DataFrame(delivery_rows))

    # Mark bus events processed
    if processed_ids:
        # DuckDB attach may not support easy bulk UPDATE with list; do per-id safe path
        for eid in set(processed_ids):
            try:
                con.execute(
                    """
                    UPDATE pg.public.event_bus
                    SET status = 'PROCESSED', processed_at = ?
                    WHERE event_id = ?
                    """,
                    [now, eid],
                )
            except Exception as e:
                logger.warning("Could not mark event %s processed: %s", eid, e)

    pending_left = qdf(
        con,
        "SELECT COUNT(*) AS n FROM pg.public.event_bus WHERE UPPER(COALESCE(status,'PENDING'))='PENDING'",
    )
    left = int(pending_left.iloc[0]["n"]) if not pending_left.empty else -1

    logger.info(
        "Queued=%s deliveries=%s events_touched=%s pending_left=%s",
        len(queue_rows),
        len(delivery_rows),
        len(set(processed_ids)),
        left,
    )
    logger.info("=== Phase 23 complete ===")


if __name__ == "__main__":
    run()