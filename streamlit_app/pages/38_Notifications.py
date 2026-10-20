"""Phase 23 — Notification delivery console.

Event Bus → queue → dry-run delivery. Email/WhatsApp are simulated until
credentials are configured. Not a live messaging service.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from components.data_access import has_error, qdf_or_error
from components.pagekit import boot, close_page
from components.ui import banner, empty_state, kpi_row, section

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
            ORDER BY created_at DESC
            LIMIT 300
            """
        ),
        "deliveries": qdf_or_error(
            """
            SELECT *
            FROM fact_notification_deliveries
            ORDER BY delivered_at DESC
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
    for token in ("does not exist", "undefinedtable", "relation", "notification", "connect")
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
            "label": "Queue rows",
            "value": f"{_len(queue):,}",
            "hint": "Recent notification queue",
            "tone": "info",
        },
        {
            "label": "Deliveries",
            "value": f"{_len(deliveries):,}",
            "hint": "Logged send attempts",
            "tone": "success",
        },
        {
            "label": "Bus still PENDING",
            "value": f"{pending:,}" if pending is not None else "—",
            "hint": "Events not yet drained",
            "tone": "warning" if (pending or 0) else "success",
        },
    ]
)

if pending is not None and pending > 200:
    banner(
        f"{pending} PENDING events remain on the bus",
        "Re-run `python ingestion/run_phase23_notifications.py` to drain.",
        tone="warning",
        icon="⏳",
    )

tab_q, tab_d, tab_cfg = st.tabs(["Queue", "Deliveries", "Channels & templates"])

with tab_q:
    section("Notification queue", "Filter by channel or status when columns exist.")
    if queue is None or queue.empty or has_error(queue):
        empty_state(
            "Queue is empty",
            "Events may be below severity threshold or already drained.",
            icon="📥",
        )
        if has_error(queue):
            st.code(str(queue.iloc[0].get("error")))
    else:
        filters = st.columns(2)
        view = queue.copy()
        with filters[0]:
            if "channel_id" in view.columns:
                opts = sorted(view["channel_id"].dropna().astype(str).unique().tolist())
                sel = st.multiselect("Channel", opts)
                if sel:
                    view = view[view["channel_id"].astype(str).isin(sel)]
        with filters[1]:
            status_col = next(
                (c for c in ("status", "queue_status", "state") if c in view.columns),
                None,
            )
            if status_col:
                opts = sorted(view[status_col].dropna().astype(str).unique().tolist())
                sel = st.multiselect("Status", opts)
                if sel:
                    view = view[view[status_col].astype(str).isin(sel)]

        st.caption(f"**{len(view):,}** queue rows")
        st.dataframe(view, use_container_width=True, hide_index=True)
        if "channel_id" in view.columns and not view.empty and not st.session_state.get(
            "low_bandwidth"
        ):
            st.bar_chart(view["channel_id"].astype(str).value_counts())

with tab_d:
    section("Delivery log", "DRY_RUN_OK / LOGGED means the pipeline completed without external APIs.")
    if deliveries is None or deliveries.empty or has_error(deliveries):
        empty_state("No deliveries yet", "Run the Phase 23 job after events exist.", icon="📨")
        if has_error(deliveries):
            st.code(str(deliveries.iloc[0].get("error")))
    else:
        st.dataframe(deliveries, use_container_width=True, hide_index=True)
        status_col = next(
            (
                c
                for c in ("delivery_status", "status", "result")
                if c in deliveries.columns
            ),
            None,
        )
        if status_col and not st.session_state.get("low_bandwidth"):
            st.bar_chart(deliveries[status_col].astype(str).value_counts())

with tab_cfg:
    section("Channels", "DRY_RUN channels are safe defaults until SMTP / WhatsApp credentials exist.")
    if channels is None or channels.empty or has_error(channels):
        empty_state("No channels configured", icon="📡")
    else:
        st.dataframe(channels, use_container_width=True, hide_index=True)

    section("Templates", "Message shapes bound to channels.")
    if templates is None or templates.empty or has_error(templates):
        empty_state("No templates", icon="📝")
    else:
        st.dataframe(templates, use_container_width=True, hide_index=True)

banner(
    "Dry-run is intentional",
    "DRY_RUN_OK / LOGGED means the pipeline worked end-to-end without calling "
    "external APIs. Wire SMTP or WhatsApp credentials later to flip channels "
    "from DRY_RUN to ACTIVE.",
    tone="info",
    icon="ℹ️",
)

close_page()
