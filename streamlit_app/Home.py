"""
OceanWatch AI — Home (operator cockpit)
KPIs, situation strip, guided next actions. Nav lives in the sidebar.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

from components import data_access as da
from components.branding import show_attribution, show_methodology
from components.ui import (
    banner,
    empty_state,
    ensure_theme,
    footer_note,
    kpi_row,
    page_header,
    section,
    status_bar,
    tile_grid,
)
from ow_theme import plotly_layout

ensure_theme()

page_header(
    "Mission cockpit",
    "A calm snapshot of Kenya EEZ / WIO activity, risk, and system readiness. "
    "Use the sidebar to dive into any domain — this page stays intentionally short.",
    kicker="OceanWatch AI · Home",
    chips=[
        ("Decision-support", "info"),
        (str(st.session_state.get("persona", "Analyst")), "primary"),
    ],
)

# ── Status strip ────────────────────────────────────────────────────────────
now = datetime.now(timezone.utc)
status_parts = [f"UTC {now.strftime('%Y-%m-%d %H:%M')}"]
db_ok = False
db_error = ""
try:
    strip = da.load_status_strip()
    db_ok = True
    if strip.get("db_ok") is False:
        db_ok = False
        db_error = str(strip.get("error") or "database unavailable")
    else:
        # fold useful strip keys into status
        for key in ("ais_age", "events_24h", "alerts_open", "last_ingest"):
            if strip.get(key) not in (None, ""):
                status_parts.append(f"{key.replace('_',' ')}: {strip[key]}")
except Exception:
    try:
        eng = da.get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_ok = True
        status_parts.append("Database connected")
    except Exception as exc:  # noqa: BLE001
        db_error = str(exc)
        db_ok = False

if not db_ok:
    status_parts.append("Database offline")
    banner(
        "Database is not reachable",
        "Start Docker Desktop and run `docker compose up -d postgres`, then refresh. "
        f"Detail: {db_error}",
        tone="warning",
        icon="⚠️",
    )
elif "Database connected" not in " ".join(status_parts):
    status_parts.append("Database connected")

if st.session_state.get("low_bandwidth"):
    status_parts.append("Low-bandwidth mode on")
if st.session_state.get("a11y_dark_mode"):
    status_parts.append("Dark mode")
if st.session_state.get("a11y_large_text"):
    status_parts.append("Large text")

status_bar(status_parts)


def _scalar(sql: str, default=0):
    if not db_ok:
        return default
    try:
        with da.get_engine().connect() as conn:
            row = conn.execute(text(sql)).fetchone()
            return row[0] if row and row[0] is not None else default
    except Exception:
        return default


def _frame(sql: str) -> pd.DataFrame:
    if not db_ok:
        return pd.DataFrame()
    try:
        return pd.read_sql(text(sql), da.get_engine())
    except Exception:
        return pd.DataFrame()


events_24h = _scalar(
    """
    SELECT COUNT(*) FROM event_bus
    WHERE COALESCE(created_at, event_time) > NOW() - INTERVAL '24 hours'
    """,
    0,
)
if events_24h == 0:
    events_24h = _scalar("SELECT COUNT(*) FROM event_bus", 0)

notif_pending = _scalar(
    """
    SELECT COUNT(*) FROM notification_queue
    WHERE LOWER(COALESCE(status,'')) IN ('pending','queued','failed','retry')
    """,
    0,
)
vessels = _scalar(
    """
    SELECT COUNT(DISTINCT mmsi) FROM ais_positions
    WHERE ts > NOW() - INTERVAL '24 hours'
    """,
    0,
)
if vessels == 0:
    vessels = _scalar("SELECT COUNT(DISTINCT mmsi) FROM vessels", 0)

risk_high = _scalar(
    """
    SELECT COUNT(*) FROM unified_risk
    WHERE LOWER(COALESCE(tier, risk_level, '')) IN ('high','critical','severe')
    """,
    0,
)

kpi_row(
    [
        {
            "label": "Events (bus)",
            "value": f"{int(events_24h):,}",
            "hint": "Published on the event bus",
            "tone": "primary",
        },
        {
            "label": "Notification backlog",
            "value": f"{int(notif_pending):,}",
            "hint": "Pending / failed deliveries",
            "tone": "warning" if int(notif_pending) else "success",
        },
        {
            "label": "Vessels (sample)",
            "value": f"{int(vessels):,}",
            "hint": "Distinct identities when AIS is loaded",
            "tone": "info",
        },
        {
            "label": "Elevated risk",
            "value": f"{int(risk_high):,}",
            "hint": "High / critical unified risk rows",
            "tone": "danger" if int(risk_high) else "success",
        },
    ]
)

# ── Guided destinations ─────────────────────────────────────────────────────
section(
    "Where do you want to go?",
    "Persona-aware shortcuts — full navigation is always in the sidebar.",
)

persona = st.session_state.get("persona", "Analyst")
persona_tiles = {
    "Executive": [
        {"icon": "📊", "title": "Executive Summary", "detail": "Board-ready posture and trends."},
        {"icon": "🛡️", "title": "Unified Risk", "detail": "Cross-domain risk in one view."},
        {"icon": "📰", "title": "WIO Intelligence Brief", "detail": "Narrative situation report."},
        {"icon": "❤️", "title": "System Health", "detail": "Freshness and pipeline confidence."},
    ],
    "Operations": [
        {"icon": "🚨", "title": "Operational Alerts", "detail": "Actionable queue for watch floor."},
        {"icon": "📡", "title": "AIS Live", "detail": "Live traffic picture."},
        {"icon": "📥", "title": "Notifications", "detail": "Delivery backlog and channels."},
        {"icon": "🔗", "title": "Event Bus", "detail": "Upstream signal fabric."},
    ],
    "Researcher": [
        {"icon": "🧪", "title": "Research Data", "detail": "Exportable scientific layers."},
        {"icon": "🌊", "title": "Bloom Risk", "detail": "Ocean color / bloom context."},
        {"icon": "🌿", "title": "Habitat Suitability", "detail": "Environmental suitability."},
        {"icon": "📚", "title": "Data Catalog", "detail": "What exists and when it refreshed."},
    ],
    "Partner": [
        {"icon": "🤝", "title": "Partner Access", "detail": "Scoped API and share policies."},
        {"icon": "📄", "title": "Intelligence Reports", "detail": "Publishable brief packages."},
        {"icon": "🧾", "title": "Audit Trail", "detail": "Who accessed what, when."},
        {"icon": "🔔", "title": "Alert Subscriptions", "detail": "Managed notification preferences."},
    ],
    "Analyst": [
        {"icon": "🛰️", "title": "Anomaly Engine", "detail": "Elevated vessel and ops signals."},
        {"icon": "🌑", "title": "Dark Activity", "detail": "AIS gaps and dark rendezvous cues."},
        {"icon": "⚓", "title": "Port Intelligence", "detail": "Port calls and congestion risk."},
        {"icon": "🔗", "title": "Event Bus", "detail": "Trace signals into notifications."},
    ],
}
tile_grid(persona_tiles.get(persona, persona_tiles["Analyst"]))
st.caption(
    "Shortcuts are guidance only — open the matching page from the sidebar "
    f"(active persona: **{persona}**)."
)

# ── Lightweight trend ───────────────────────────────────────────────────────
section("Signal pulse", "Recent event volume when the bus is populated.")

trend = _frame(
    """
    SELECT DATE_TRUNC('hour', COALESCE(created_at, event_time)) AS bucket,
           COUNT(*)::int AS events
    FROM event_bus
    WHERE COALESCE(created_at, event_time) > NOW() - INTERVAL '48 hours'
    GROUP BY 1
    ORDER BY 1
    """
)

low_bw = bool(st.session_state.get("low_bandwidth"))
if trend.empty:
    empty_state(
        "No event-bus pulse yet",
        "Run phase-22 publish jobs after Postgres is up to populate this chart.",
        icon="📈",
    )
elif low_bw:
    st.dataframe(
        trend.rename(columns={"bucket": "Hour (UTC)", "events": "Events"}),
        use_container_width=True,
        hide_index=True,
    )
else:
    fig = px.area(
        trend,
        x="bucket",
        y="events",
        labels={"bucket": "Hour (UTC)", "events": "Events"},
    )
    fig.update_layout(**plotly_layout(title={"text": "Event bus volume · last 48h"}))
    fig.update_traces(line_color="#0B6E99", fillcolor="rgba(11,110,153,0.18)")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# ── Attention queue ─────────────────────────────────────────────────────────
section("Attention queue", "Newest notifications or events when available.")

alerts = _frame(
    """
    SELECT id, channel, status, created_at,
           COALESCE(title, subject, message) AS title
    FROM notification_queue
    ORDER BY created_at DESC NULLS LAST
    LIMIT 12
    """
)
if alerts.empty:
    alerts = _frame(
        """
        SELECT event_id AS id, event_type AS channel, severity AS status,
               created_at, COALESCE(summary, title, payload::text) AS title
        FROM event_bus
        ORDER BY created_at DESC NULLS LAST
        LIMIT 12
        """
    )

if alerts.empty:
    empty_state(
        "Queue is clear (or not initialized)",
        "When notifications or events exist, the newest items appear here.",
        icon="✅",
    )
else:
    st.dataframe(alerts, use_container_width=True, hide_index=True)

show_methodology()
show_attribution()
footer_note()
