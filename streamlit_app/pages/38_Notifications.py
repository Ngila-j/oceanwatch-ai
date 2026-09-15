"""Phase 23 — Notification delivery console."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

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

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=45)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "channels": q("SELECT * FROM dim_notification_channels ORDER BY channel_id"),
        "templates": q("SELECT * FROM dim_notification_templates ORDER BY template_id"),
        "queue": q(
            """
            SELECT * FROM fact_notification_queue
            ORDER BY created_at DESC
            LIMIT 300
            """
        ),
        "deliveries": q(
            """
            SELECT * FROM fact_notification_deliveries
            ORDER BY delivered_at DESC
            LIMIT 300
            """
        ),
        "pending": q(
            """
            SELECT COUNT(*) AS pending
            FROM event_bus
            WHERE UPPER(COALESCE(status, 'PENDING')) = 'PENDING'
            """
        ),
    }


d = load()

if d["queue"] is None or (d["queue"].empty and "error" not in (d["queue"].columns if not d["queue"].empty else [])):
    if d["channels"] is None or d["channels"].empty or "error" in d["channels"].columns:
        st.warning(
            "No Phase 23 data. Run init_phase23_notifications.py and run_phase23_notifications.py"
        )
        st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Channels", len(d["channels"]) if d["channels"] is not None else 0)
c2.metric("Queue rows", len(d["queue"]) if d["queue"] is not None else 0)
c3.metric("Deliveries", len(d["deliveries"]) if d["deliveries"] is not None else 0)
pending = None
if d["pending"] is not None and not d["pending"].empty and "pending" in d["pending"].columns:
    pending = int(d["pending"].iloc[0]["pending"])
c4.metric("Bus PENDING left", pending if pending is not None else "—")

st.subheader("Channels")
st.dataframe(d["channels"], width="stretch")

st.subheader("Templates")
st.dataframe(d["templates"], width="stretch")

st.subheader("Queue")
if d["queue"] is not None and not d["queue"].empty and "error" not in d["queue"].columns:
    st.dataframe(d["queue"], width="stretch")
    if "channel_id" in d["queue"].columns:
        st.bar_chart(d["queue"]["channel_id"].value_counts())
else:
    st.caption("No queue items (all events may have been below severity threshold)")

st.subheader("Deliveries")
if d["deliveries"] is not None and not d["deliveries"].empty and "error" not in d["deliveries"].columns:
    st.dataframe(d["deliveries"], width="stretch")
else:
    st.caption("No deliveries")

st.info(
    "DRY_RUN_OK / LOGGED means the pipeline worked end-to-end without calling external APIs. "
    "Wire SMTP or WhatsApp credentials later to flip channels from DRY_RUN to ACTIVE."
)