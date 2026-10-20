"""Phase 23 — Notification delivery console.

Event Bus → queue → dry-run delivery. Email/WhatsApp are simulated until
credentials are configured. Not a live messaging service.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Notifications",
    page_icon=":material/notifications_active:",
    layout="wide",
)

st.title("Notification Delivery")
st.caption(
    "Event Bus → queue → dry-run delivery. Email/WhatsApp are simulated until "
    "credentials are configured. Not a live messaging service yet."
)

try:
    from components.branding import attribution_footer, methodology_blurb
except Exception:  # pragma: no cover
    def attribution_footer():  # type: ignore
        pass

    def methodology_blurb():  # type: ignore
        pass


try:
    from components.data_access import has_error, qdf_or_error
except Exception as exc:  # pragma: no cover
    st.error(f"Data access layer unavailable: {exc}")
    st.stop()


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


with st.sidebar:
    if st.button("Refresh now", use_container_width=True):
        load.clear()
        st.rerun()

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
    t in schema_error.lower()
    for t in ("does not exist", "undefinedtable", "relation", "notification")
):
    st.warning(
        "No Phase 23 data yet. Initialise and run:\n\n"
        "```bash\n"
        "python ingestion/init_phase23_notifications.py\n"
        "python ingestion/run_phase23_notifications.py\n"
        "```"
    )
    with st.expander("Diagnostics"):
        st.code(schema_error)
    st.stop()

pending = None
if pending_df is not None and not pending_df.empty and not has_error(pending_df):
    if "pending" in pending_df.columns:
        try:
            pending = int(pending_df.iloc[0]["pending"])
        except Exception:
            pending = None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Channels", 0 if channels is None or has_error(channels) else len(channels))
c2.metric("Queue rows", 0 if queue is None or has_error(queue) else len(queue))
c3.metric("Deliveries", 0 if deliveries is None or has_error(deliveries) else len(deliveries))
c4.metric("Bus PENDING left", pending if pending is not None else "—")

tab_q, tab_d, tab_cfg = st.tabs(["Queue", "Deliveries", "Channels & templates"])

with tab_q:
    if queue is None or queue.empty or has_error(queue):
        st.caption("No queue items (events may be below severity threshold or already drained).")
        if has_error(queue):
            st.code(str(queue.iloc[0].get("error")))
    else:
        if "channel_id" in queue.columns:
            sel = st.multiselect(
                "Channel filter",
                sorted(queue["channel_id"].dropna().astype(str).unique().tolist()),
                default=None,
            )
            view = queue[queue["channel_id"].astype(str).isin(sel)] if sel else queue
        else:
            view = queue
        st.dataframe(view, width="stretch", hide_index=True)
        if "channel_id" in view.columns and not view.empty:
            st.bar_chart(view["channel_id"].value_counts())

with tab_d:
    if deliveries is None or deliveries.empty or has_error(deliveries):
        st.caption("No deliveries yet.")
        if has_error(deliveries):
            st.code(str(deliveries.iloc[0].get("error")))
    else:
        st.dataframe(deliveries, width="stretch", hide_index=True)
        if "delivery_status" in deliveries.columns:
            st.bar_chart(deliveries["delivery_status"].value_counts())

with tab_cfg:
    st.subheader("Channels")
    if channels is None or channels.empty or has_error(channels):
        st.caption("No channels")
    else:
        st.dataframe(channels, width="stretch", hide_index=True)

    st.subheader("Templates")
    if templates is None or templates.empty or has_error(templates):
        st.caption("No templates")
    else:
        st.dataframe(templates, width="stretch", hide_index=True)

st.info(
    "DRY_RUN_OK / LOGGED means the pipeline worked end-to-end without calling external APIs. "
    "Wire SMTP or WhatsApp credentials later to flip channels from DRY_RUN to ACTIVE."
)

if pending is not None and pending > 200:
    st.warning(
        f"{pending} PENDING events remain on the bus — re-run "
        "`python ingestion/run_phase23_notifications.py`."
    )

try:
    methodology_blurb()
    attribution_footer()
except Exception:
    pass
