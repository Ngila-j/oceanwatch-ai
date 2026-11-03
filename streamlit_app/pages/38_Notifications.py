"""Phase 23 — Notification delivery console.

Event Bus → queue → dry-run delivery. Email/WhatsApp are simulated until
credentials are configured. Not a live messaging service.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.data_access import has_error, qdf_or_error
from components.pagekit import banner, boot, close_page, kpi_row

boot(
    "Notifications",
    "Delivery console for OceanWatch alerts. Events leave the bus, land in a "
    "queue, and are dry-run delivered until real channels are wired.",
    kicker="Operations fabric · Phase 23",
    chips=[
        ("Dry-run safe", "success"),
        ("Not live SMS/email", "warning"),
    ],
    page_title="Notifications · OceanWatch",
    icon="📥",
)

with st.sidebar:
    st.markdown("### Notification tools")
    if st.button("Refresh notifications", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()


@st.cache_data(ttl=45, show_spinner="Loading notifications…")
def load() -> dict[str, pd.DataFrame]:
    return {
        "channels": qdf_or_error(
            "SELECT * FROM dim_notification_channels ORDER BY channel_id"
        ),
        "templates": qdf_or_error(
            "SELECT * FROM dim_notification_templates ORDER BY template_id"
        ),
        "queue": qdf_or_error(
            """
            SELECT *
            FROM fact_notification_queue
            ORDER BY created_at DESC NULLS LAST
            LIMIT 300
            """
        ),
        "deliveries": qdf_or_error(
            """
            SELECT *
            FROM fact_notification_deliveries
            ORDER BY delivered_at DESC NULLS LAST
            LIMIT 300
            """
        ),
        "pending": qdf_or_error(
            """
            SELECT COUNT(*) AS pending
            FROM event_bus
            WHERE UPPER(COALESCE(status, 'PENDING')) = 'PENDING'
            """
        ),
    }


d = load()
channels = d["channels"]
templates = d["templates"]
queue = d["queue"]
deliveries = d["deliveries"]
pending_df = d["pending"]

schema_error = None
for frame in (channels, templates, queue, deliveries):
    if has_error(frame):
        schema_error = str(frame.iloc[0].get("error"))
        break

if schema_error and any(
    token in schema_error.lower()
    for token in ("does not exist", "undefinedtable", "relation", "notification")
):
    banner(
        "Notification tables not ready",
        "Initialise Phase 23, drain the bus, then refresh.",
        tone="warning",
        icon="⚠️",
    )
    st.code(
        "python ingestion/init_phase23_notifications.py\n"
        "python ingestion/run_phase23_notifications.py",
        language="bash",
    )
    with st.expander("Diagnostics", expanded=False):
        st.code(schema_error)
    close_page()
    st.stop()


def _len(df: pd.DataFrame) -> int:
    if df is None or df.empty or has_error(df):
        return 0
    return int(len(df))


pending = None
if pending_df is not None and not pending_df.empty and not has_error(pending_df):
    if "pending" in pending_df.columns:
        try:
            pending = int(pending_df.iloc[0]["pending"])
        except Exception:
            pending = None

kpi_row(
    [
        {
            "label": "Channels",
            "value": f"{_len(channels):,}",
            "hint": "Configured delivery channels",
            "tone": "primary",
        },
        {
            "label": "Templates",
            "value": f"{_len(templates):,}",
            "hint": "Topic → message templates",
            "tone": "neutral",
        },
        {
            "label": "Queue",
            "value": f"{_len(queue):,}",
            "hint": "Recent queue rows (cap 300)",
            "tone": "info",
        },
        {
            "label": "Deliveries",
            "value": f"{_len(deliveries):,}",
            "hint": "Dry-run delivery log",
            "tone": "success",
        },
        {
            "label": "Bus pending",
            "value": "—" if pending is None else f"{pending:,}",
            "hint": "PENDING on event_bus",
            "tone": "warning" if (pending or 0) else "success",
        },
    ]
)

if pending is not None and pending > 200:
    banner(
        f"{pending} PENDING events remain on the bus",
        "Re-run `python ingestion/run_phase23_notifications.py` to drain more.",
        tone="warning",
        icon="⏳",
    )

tab_ch, tab_tpl, tab_q, tab_d = st.tabs(
    ["Channels", "Templates", "Queue", "Deliveries"]
)

with tab_ch:
    if has_error(channels) or channels is None or channels.empty:
        st.info("No channels yet. Run Phase 23 init.")
    else:
        st.dataframe(channels, use_container_width=True, hide_index=True)

with tab_tpl:
    if has_error(templates) or templates is None or templates.empty:
        st.info("No templates yet. Run Phase 23 runner.")
    else:
        st.dataframe(templates, use_container_width=True, hide_index=True)

with tab_q:
    if has_error(queue) or queue is None or queue.empty:
        st.info("Queue empty. Drain the event bus with the Phase 23 runner.")
    else:
        show = queue.copy()
        prefer = [
            c
            for c in (
                "created_at",
                "status",
                "topic",
                "event_type",
                "severity",
                "channel_id",
                "recipient",
                "subject",
                "event_id",
                "queue_id",
            )
            if c in show.columns
        ]
        st.dataframe(
            show[prefer] if prefer else show,
            use_container_width=True,
            hide_index=True,
        )

with tab_d:
    if has_error(deliveries) or deliveries is None or deliveries.empty:
        st.info("No delivery rows yet.")
    else:
        show = deliveries.copy()
        prefer = [
            c
            for c in (
                "delivered_at",
                "delivery_status",
                "channel_id",
                "recipient",
                "response_code",
                "response_message",
                "event_id",
                "queue_id",
                "delivery_id",
            )
            if c in show.columns
        ]
        st.dataframe(
            show[prefer] if prefer else show,
            use_container_width=True,
            hide_index=True,
        )

with st.expander("How delivery works", expanded=False):
    st.markdown(
        """
1. Domain events land on `event_bus` (Phase 22).
2. Phase 23 consumes **PENDING** rows, matches templates by topic, and enqueues
   fan-out to **log** (always) plus **email** / **whatsapp** at WATCH+.
3. Deliveries are **dry-run** — status `DRY_RUN_OK` / `LOGGED`. No live SMS/email
   until channel credentials are configured outside this prototype.
4. Source events are marked **PROCESSED**.
        """
    )

banner(
    "Methodology & caveats",
    "OceanWatch AI is a decision-support prototype for Kenya EEZ / Western Indian "
    "Ocean monitoring. Outputs are indicative, not authoritative.\n\n"
    "AIS and satellite products can lag or contain gaps.\n"
    "Risk scores are model-assisted heuristics — always corroborate with primary sources.\n"
    "Environmental layers depend on open data availability and refresh cadence.\n"
    "See System Health for data freshness and quality.\n\n"
    "Data sources may include AIS aggregators, Global Fishing Watch, open ocean color / "
    "SST products, and internal OceanWatch pipelines. Attribution on each page.",
    tone="info",
    icon="ℹ️",
)

close_page()
