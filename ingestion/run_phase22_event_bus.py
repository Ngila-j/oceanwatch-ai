"""
Phase 22 complete — lightweight Event Bus.
Publishes domain events from existing fact tables into event_bus (Postgres).
No Kafka required; suitable for local/free deployment.
"""

import json
import logging
import random
from datetime import datetime

import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase22_bus_v1.0"
REGION = "kenya_eez"
COUNTRY = "KE"


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


def write(con, table, df):
    if df is None or df.empty:
        logger.info("%s: 0 rows", table)
        return
    use = [c for c in df.columns if c in cols(con, table)]
    if not use:
        logger.warning("No columns for %s", table)
        return
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


def payload_from_row(row, max_len=800):
    try:
        d = {k: (str(v) if not isinstance(v, (int, float, bool, type(None))) else v) for k, v in dict(row).items()}
        s = json.dumps(d, default=str)
        return s[:max_len]
    except Exception:
        return str(dict(row))[:max_len]


def emit(events, topic, event_type, severity, row, source_table, now):
    events.append(
        dict(
            event_id=random.randint(10_000_000, 99_999_999),
            topic=topic,
            event_type=event_type,
            severity=severity or "INFO",
            payload=payload_from_row(row),
            region_id=REGION,
            country_id=COUNTRY,
            source_table=source_table,
            status="PENDING",
            created_at=now,
            processed_at=None,
            model_version=MODEL,
        )
    )


def run():
    logger.info("=== Phase 22 Event Bus ===")
    now = datetime.utcnow()
    con = connect()

    topics = pd.DataFrame(
        [
            dict(topic="maritime.events", description="Vessel state / geofence / behaviour events", status="ACTIVE"),
            dict(topic="risk.unified", description="Unified risk composite updates", status="ACTIVE"),
            dict(topic="ocean.state", description="Ocean state engine outputs", status="ACTIVE"),
            dict(topic="fisheries.alerts", description="Fisheries heuristic alerts", status="ACTIVE"),
            dict(topic="ops.alerts", description="Operational fact_alerts fan-out", status="ACTIVE"),
            dict(topic="system.health", description="Platform health signals", status="ACTIVE"),
        ]
    )
    write(con, "event_bus_topics", topics)

    consumers = pd.DataFrame(
        [
            dict(
                consumer_id="streamlit_ui",
                consumer_name="Streamlit Event Viewer",
                topics="maritime.events,risk.unified,ocean.state,ops.alerts",
                status="ACTIVE",
                last_seen_at=now,
            ),
            dict(
                consumer_id="alert_dispatcher",
                consumer_name="Notification dry-run consumer",
                topics="ops.alerts,fisheries.alerts,risk.unified",
                status="ACTIVE",
                last_seen_at=now,
            ),
            dict(
                consumer_id="api_gateway",
                consumer_name="FastAPI future subscriber",
                topics="risk.unified,ocean.state,maritime.events",
                status="PLANNED",
                last_seen_at=None,
            ),
        ]
    )
    write(con, "event_bus_consumers", consumers)

    events = []

    # Maritime events
    ve = qdf(con, "SELECT * FROM pg.public.fact_vessel_events ORDER BY event_time DESC LIMIT 100")
    for _, row in ve.iterrows():
        emit(
            events,
            "maritime.events",
            str(row.get("event_type") or "VESSEL_EVENT"),
            str(row.get("severity") or "INFO"),
            row,
            "fact_vessel_events",
            now,
        )

    # Unified risk
    ur = qdf(con, "SELECT * FROM pg.public.fact_unified_risk_composite ORDER BY as_of_date DESC LIMIT 5")
    for _, row in ur.iterrows():
        emit(
            events,
            "risk.unified",
            "COMPOSITE_RISK",
            str(row.get("composite_level") or "INFO"),
            row,
            "fact_unified_risk_composite",
            now,
        )

    # Ocean state
    os_ = qdf(con, "SELECT * FROM pg.public.fact_ocean_state ORDER BY as_of_date DESC LIMIT 5")
    for _, row in os_.iterrows():
        emit(
            events,
            "ocean.state",
            "OCEAN_STATE",
            str(row.get("ocean_state_label") or "INFO"),
            row,
            "fact_ocean_state",
            now,
        )

    # Fisheries alerts
    fa = qdf(con, "SELECT * FROM pg.public.fact_fisheries_alerts LIMIT 50")
    for _, row in fa.iterrows():
        emit(
            events,
            "fisheries.alerts",
            str(row.get("alert_type") or "FISHERIES_ALERT"),
            str(row.get("severity") or "INFO"),
            row,
            "fact_fisheries_alerts",
            now,
        )

    # Operational alerts
    oa = qdf(
        con,
        """
        SELECT * FROM pg.public.fact_alerts
        WHERE UPPER(COALESCE(status, 'OPEN')) = 'OPEN'
        ORDER BY created_at DESC
        LIMIT 50
        """,
    )
    for _, row in oa.iterrows():
        emit(
            events,
            "ops.alerts",
            str(row.get("alert_type") or row.get("category") or "OPS_ALERT"),
            str(row.get("severity") or "INFO"),
            row,
            "fact_alerts",
            now,
        )

    # System health (optional)
    sh = qdf(con, "SELECT * FROM pg.public.fact_system_health ORDER BY checked_at DESC LIMIT 10")
    if sh.empty:
        sh = qdf(con, "SELECT * FROM pg.public.fact_system_health LIMIT 10")
    for _, row in sh.iterrows():
        emit(
            events,
            "system.health",
            "HEALTH_CHECK",
            "INFO",
            row,
            "fact_system_health",
            now,
        )

    write(con, "event_bus", pd.DataFrame(events))

    # Topic summary
    if events:
        by_topic = pd.DataFrame(events).groupby("topic").size().to_dict()
        logger.info("Published by topic: %s", by_topic)
    logger.info("Total events=%s", len(events))
    logger.info("=== Phase 22 complete ===")


if __name__ == "__main__":
    run()