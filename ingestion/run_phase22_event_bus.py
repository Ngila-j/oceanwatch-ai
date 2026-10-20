"""
Phase 22 — lightweight Event Bus publisher.

Publishes domain events from existing fact tables into event_bus (Postgres).
No Kafka required; suitable for local/free deployment.

Design fixes vs earlier draft:
- Does NOT wipe event_bus on each run (preserves PENDING + audit trail)
- Stable event_id / source_key for idempotent inserts
- Shared db_utils for URI + connection lifecycle
- Narrow SQL projections instead of SELECT *
- Registry (topics/consumers) still replaced as a small dim set
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

_INGESTION_DIR = Path(__file__).resolve().parent
if str(_INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(_INGESTION_DIR))

from db_utils import pg_connection, qdf, upsert_consumers, upsert_topics, write_frame

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MODEL = "phase22_bus_v1.1"
REGION = "kenya_eez"
COUNTRY = "KE"

TOPICS = [
    dict(
        topic="maritime.events",
        description="Vessel state / geofence / behaviour events",
        status="ACTIVE",
    ),
    dict(
        topic="risk.unified",
        description="Unified risk composite updates",
        status="ACTIVE",
    ),
    dict(
        topic="ocean.state",
        description="Ocean state engine outputs",
        status="ACTIVE",
    ),
    dict(
        topic="fisheries.alerts",
        description="Fisheries heuristic alerts",
        status="ACTIVE",
    ),
    dict(
        topic="ops.alerts",
        description="Operational fact_alerts fan-out",
        status="ACTIVE",
    ),
    dict(
        topic="system.health",
        description="Platform health signals",
        status="ACTIVE",
    ),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _stable_id(*parts: Any) -> int:
    """Deterministic positive BIGINT-ish id from natural key parts."""
    raw = "|".join("" if p is None else str(p) for p in parts)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    # Keep in signed BIGINT-safe positive range
    return int(digest[:15], 16)


def _source_key(source_table: str, *parts: Any) -> str:
    raw = "|".join("" if p is None else str(p) for p in parts)
    return f"{source_table}:{hashlib.sha1(raw.encode('utf-8')).hexdigest()[:24]}"


def _json_payload(row: Any, keep: Optional[Iterable[str]] = None, max_len: int = 2000) -> str:
    try:
        data = dict(row) if not isinstance(row, dict) else dict(row)
        if keep is not None:
            keep_set = set(keep)
            data = {k: v for k, v in data.items() if k in keep_set}
        cleaned = {
            k: (v if isinstance(v, (int, float, bool, type(None))) else str(v))
            for k, v in data.items()
        }
        return json.dumps(cleaned, default=str)[:max_len]
    except Exception:
        return "{}"


def _emit(
    bucket: list[dict],
    *,
    topic: str,
    event_type: str,
    severity: str,
    source_table: str,
    natural_parts: tuple[Any, ...],
    payload_row: Any,
    payload_keep: Optional[Iterable[str]],
    now: datetime,
) -> None:
    sk = _source_key(source_table, topic, event_type, *natural_parts)
    bucket.append(
        dict(
            event_id=_stable_id(sk),
            topic=topic,
            event_type=str(event_type or "EVENT")[:120],
            severity=str(severity or "INFO").upper()[:32],
            payload=_json_payload(payload_row, keep=payload_keep),
            region_id=REGION,
            country_id=COUNTRY,
            source_table=source_table,
            source_key=sk,
            status="PENDING",
            created_at=now,
            processed_at=None,
            model_version=MODEL,
        )
    )


def _existing_source_keys(con, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    # Chunk to avoid oversized IN lists
    found: set[str] = set()
    chunk_size = 400
    for i in range(0, len(keys), chunk_size):
        chunk = keys[i : i + chunk_size]
        placeholders = ", ".join(["?"] * len(chunk))
        df = qdf(
            con,
            f"""
            SELECT source_key
            FROM pg.public.event_bus
            WHERE source_key IN ({placeholders})
            """,
            chunk,
        )
        if not df.empty and "source_key" in df.columns:
            found.update(df["source_key"].dropna().astype(str).tolist())
    return found


def _publish_new(con, events: list[dict]) -> int:
    if not events:
        logger.info("event_bus: 0 new events")
        return 0
    df = pd.DataFrame(events)
    existing = _existing_source_keys(con, df["source_key"].astype(str).tolist())
    fresh = df[~df["source_key"].astype(str).isin(existing)]
    if fresh.empty:
        logger.info("event_bus: 0 new events (%s already present)", len(df))
        return 0
    return write_frame(con, "event_bus", fresh, replace=False)


def _collect_maritime(con, events: list[dict], now: datetime) -> None:
    ve = qdf(
        con,
        """
        SELECT
            event_id, mmsi, event_type, severity, event_time,
            lat, lon, state_label, geofence_id, notes
        FROM pg.public.fact_vessel_events
        ORDER BY event_time DESC
        LIMIT 150
        """,
    )
    for _, row in ve.iterrows():
        natural = (
            row.get("event_id"),
            row.get("mmsi"),
            row.get("event_type"),
            row.get("event_time"),
        )
        _emit(
            events,
            topic="maritime.events",
            event_type=str(row.get("event_type") or "VESSEL_EVENT"),
            severity=str(row.get("severity") or "INFO"),
            source_table="fact_vessel_events",
            natural_parts=natural,
            payload_row=row,
            payload_keep=[
                "event_id",
                "mmsi",
                "event_type",
                "severity",
                "event_time",
                "lat",
                "lon",
                "state_label",
                "geofence_id",
                "notes",
            ],
            now=now,
        )


def _collect_unified_risk(con, events: list[dict], now: datetime) -> None:
    ur = qdf(
        con,
        """
        SELECT
            region_id, country_id, as_of_date, composite_score,
            composite_level, confidence, freshness_hours, top_drivers
        FROM pg.public.fact_unified_risk_composite
        ORDER BY as_of_date DESC
        LIMIT 10
        """,
    )
    for _, row in ur.iterrows():
        natural = (row.get("region_id"), row.get("as_of_date"), row.get("composite_level"))
        _emit(
            events,
            topic="risk.unified",
            event_type="COMPOSITE_RISK",
            severity=str(row.get("composite_level") or "INFO"),
            source_table="fact_unified_risk_composite",
            natural_parts=natural,
            payload_row=row,
            payload_keep=[
                "region_id",
                "country_id",
                "as_of_date",
                "composite_score",
                "composite_level",
                "confidence",
                "freshness_hours",
                "top_drivers",
            ],
            now=now,
        )


def _collect_ocean_state(con, events: list[dict], now: datetime) -> None:
    os_ = qdf(
        con,
        """
        SELECT
            region_id, as_of_date, ocean_state_label, sst_anomaly,
            chlorophyll_risk, wave_risk, confidence
        FROM pg.public.fact_ocean_state
        ORDER BY as_of_date DESC
        LIMIT 10
        """,
    )
    for _, row in os_.iterrows():
        natural = (row.get("region_id"), row.get("as_of_date"), row.get("ocean_state_label"))
        _emit(
            events,
            topic="ocean.state",
            event_type="OCEAN_STATE",
            severity=str(row.get("ocean_state_label") or "INFO"),
            source_table="fact_ocean_state",
            natural_parts=natural,
            payload_row=row,
            payload_keep=[
                "region_id",
                "as_of_date",
                "ocean_state_label",
                "sst_anomaly",
                "chlorophyll_risk",
                "wave_risk",
                "confidence",
            ],
            now=now,
        )


def _collect_fisheries(con, events: list[dict], now: datetime) -> None:
    fa = qdf(
        con,
        """
        SELECT
            alert_id, alert_type, severity, status, region_id,
            created_at, title, summary
        FROM pg.public.fact_fisheries_alerts
        ORDER BY created_at DESC
        LIMIT 80
        """,
    )
    for _, row in fa.iterrows():
        natural = (row.get("alert_id"), row.get("alert_type"), row.get("created_at"))
        _emit(
            events,
            topic="fisheries.alerts",
            event_type=str(row.get("alert_type") or "FISHERIES_ALERT"),
            severity=str(row.get("severity") or "INFO"),
            source_table="fact_fisheries_alerts",
            natural_parts=natural,
            payload_row=row,
            payload_keep=[
                "alert_id",
                "alert_type",
                "severity",
                "status",
                "region_id",
                "created_at",
                "title",
                "summary",
            ],
            now=now,
        )


def _collect_ops_alerts(con, events: list[dict], now: datetime) -> None:
    oa = qdf(
        con,
        """
        SELECT
            alert_id, alert_type, category, severity, status,
            region_id, created_at, title, message
        FROM pg.public.fact_alerts
        WHERE UPPER(COALESCE(status, 'OPEN')) IN ('OPEN', 'ACTIVE', 'PENDING')
        ORDER BY created_at DESC
        LIMIT 80
        """,
    )
    for _, row in oa.iterrows():
        natural = (row.get("alert_id"), row.get("alert_type"), row.get("created_at"))
        _emit(
            events,
            topic="ops.alerts",
            event_type=str(row.get("alert_type") or row.get("category") or "OPS_ALERT"),
            severity=str(row.get("severity") or "INFO"),
            source_table="fact_alerts",
            natural_parts=natural,
            payload_row=row,
            payload_keep=[
                "alert_id",
                "alert_type",
                "category",
                "severity",
                "status",
                "region_id",
                "created_at",
                "title",
                "message",
            ],
            now=now,
        )


def _collect_system_health(con, events: list[dict], now: datetime) -> None:
    sh = qdf(
        con,
        """
        SELECT
            component, status, checked_at, latency_ms, message, details
        FROM pg.public.fact_system_health
        ORDER BY checked_at DESC
        LIMIT 20
        """,
    )
    for _, row in sh.iterrows():
        natural = (row.get("component"), row.get("checked_at"), row.get("status"))
        _emit(
            events,
            topic="system.health",
            event_type="HEALTH_CHECK",
            severity="INFO" if str(row.get("status") or "").upper() in {"OK", "HEALTHY", "UP"} else "WATCH",
            source_table="fact_system_health",
            natural_parts=natural,
            payload_row=row,
            payload_keep=[
                "component",
                "status",
                "checked_at",
                "latency_ms",
                "message",
                "details",
            ],
            now=now,
        )


def _consumers(now: datetime) -> list[dict]:
    return [
        dict(
            consumer_id="streamlit_ui",
            consumer_name="Streamlit Event Viewer",
            topics="maritime.events,risk.unified,ocean.state,ops.alerts,fisheries.alerts,system.health",
            status="ACTIVE",
            last_seen_at=now,
        ),
        dict(
            consumer_id="alert_dispatcher",
            consumer_name="Notification dry-run consumer",
            topics="ops.alerts,fisheries.alerts,risk.unified,maritime.events",
            status="ACTIVE",
            last_seen_at=now,
        ),
        dict(
            consumer_id="api_gateway",
            consumer_name="FastAPI future subscriber",
            topics="risk.unified,ocean.state,maritime.events",
            status="ACTIVE",
            last_seen_at=now,
        ),
    ]


def run() -> None:
    logger.info("=== Phase 22 Event Bus ===")
    now = _utcnow()
    events: list[dict] = []

    with pg_connection() as con:
        upsert_topics(con, TOPICS)
        upsert_consumers(con, _consumers(now))

        _collect_maritime(con, events, now)
        _collect_unified_risk(con, events, now)
        _collect_ocean_state(con, events, now)
        _collect_fisheries(con, events, now)
        _collect_ops_alerts(con, events, now)
        _collect_system_health(con, events, now)

        n_new = _publish_new(con, events)

        if events:
            by_topic = pd.DataFrame(events).groupby("topic").size().to_dict()
            logger.info("Candidates by topic: %s", by_topic)
        logger.info("Published %s new events (of %s candidates)", n_new, len(events))

    logger.info("=== Phase 22 complete ===")


if __name__ == "__main__":
    run()
