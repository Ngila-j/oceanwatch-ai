"""Operational Alerts — prefer oceanwatch_events when available."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Operational Alerts", page_icon=":material/warning:", layout="wide")
st.title("Operational Alerts")
st.caption(
    "Priority signals for Kenya EEZ / Mombasa. "
    "Events from the detector are preferred when present; otherwise OPEN fact_alerts."
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

    events = q(
        """
        SELECT
            created_at,
            event_type,
            event_category AS category,
            severity,
            title,
            risk_score,
            confidence_score,
            evidence,
            source,
            status,
            model_version
        FROM oceanwatch_events
        WHERE status = 'OPEN'
        ORDER BY risk_score DESC NULLS LAST, created_at DESC
        LIMIT 100
        """
    )

    alerts = q(
        """
        SELECT
            created_at,
            category,
            severity,
            title,
            risk_score,
            status
        FROM fact_alerts
        WHERE status = 'OPEN'
        ORDER BY risk_score DESC NULLS LAST, created_at DESC
        LIMIT 100
        """
    )

    gfw = q(
        """
        SELECT
            COUNT(*) AS cells,
            COALESCE(SUM(hours), 0) AS total_hours,
            MIN(effort_date) AS start_date,
            MAX(effort_date) AS end_date
        FROM fact_gfw_fishing_effort
        """
    )

    counts = q(
        """
        SELECT status, COUNT(*) AS n FROM fact_alerts GROUP BY status
        """
    )

    return events, alerts, gfw, counts


events, alerts, gfw, counts = load()

has_events = (
    events is not None
    and not events.empty
    and "error" not in events.columns
)

c1, c2, c3 = st.columns(3)
if has_events:
    c1.metric("OPEN events", len(events))
    c2.metric("Source", "oceanwatch_events")
else:
    open_n = "—"
    if counts is not None and not counts.empty and "error" not in counts.columns:
        row = counts[counts["status"] == "OPEN"]
        if not row.empty:
            open_n = int(row.iloc[0]["n"])
    c1.metric("OPEN alerts", open_n)
    c2.metric("Source", "fact_alerts")
c3.metric("GFW cells (stored)", int(gfw.iloc[0]["cells"]) if gfw is not None and not gfw.empty and "error" not in gfw.columns else "—")

if gfw is not None and not gfw.empty and "error" not in gfw.columns:
    st.caption(
        f"GFW effort (stored): {float(gfw.iloc[0].get('total_hours') or 0):.1f} hours · "
        f"{gfw.iloc[0].get('start_date')} to {gfw.iloc[0].get('end_date')} · "
        "Powered by Global Fishing Watch — https://globalfishingwatch.org"
    )

st.subheader("Priority feed")
if has_events:
    st.success("Showing oceanwatch_events (detector).")
    st.dataframe(events, width="stretch")
elif alerts is not None and not alerts.empty and "error" not in alerts.columns:
    st.info("No OPEN events — falling back to fact_alerts.")
    st.dataframe(alerts, width="stretch")
else:
    st.warning("No OPEN events or alerts.")

with st.expander("Legacy OPEN fact_alerts (always available)"):
    if alerts is not None and not alerts.empty and "error" not in alerts.columns:
        st.dataframe(alerts, width="stretch")
    else:
        st.caption("No rows.")

st.caption(
    "Vessel-related signals are for human review only. "
    "Not a legal determination. Decision-support prototype."
)