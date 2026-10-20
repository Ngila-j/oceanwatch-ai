import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime, timezone

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        return "postgresql+psycopg2://postgres:password@localhost:5433/oceanwatch_db"


try:
    from ow_theme import page_header, close_page
except ImportError:
    def page_header(title, subtitle=""):
        st.title(title)
        if subtitle:
            st.caption(subtitle)

    def close_page():
        pass


page_header("Executive Summary", "Operational snapshot — alerts, port, ocean anomalies")
st.caption(
    f"Last refreshed: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
)


@st.cache_data(ttl=120)
def load_summary():
    engine = create_engine(get_db_uri(), pool_pre_ping=True)
    empty = pd.DataFrame()
    try:
        alerts = pd.read_sql(
            """
            SELECT category, severity, title, risk_score, status, created_at
            FROM fact_alerts
            WHERE status = 'OPEN'
            ORDER BY
                CASE severity
                    WHEN 'CRITICAL' THEN 1
                    WHEN 'ELEVATED' THEN 2
                    WHEN 'WATCH' THEN 3
                    ELSE 4
                END,
                created_at DESC
            LIMIT 10
            """,
            engine,
        )
    except Exception as exc:
        st.warning(f"Alerts unavailable: {exc.__class__.__name__}")
        alerts = empty

    try:
        port = pd.read_sql(
            """
            SELECT metric_date, port_name, active_vessels, congestion_index,
                   congestion_level, avg_waiting_hours
            FROM fact_port_metrics
            ORDER BY metric_date DESC
            LIMIT 14
            """,
            engine,
        )
    except Exception as exc:
        st.warning(f"Port metrics unavailable: {exc.__class__.__name__}")
        port = empty

    try:
        anomalies = pd.read_sql(
            "SELECT * FROM fact_ocean_anomalies ORDER BY created_at DESC LIMIT 20",
            engine,
        )
    except Exception as exc:
        st.warning(f"Ocean anomalies unavailable: {exc.__class__.__name__}")
        anomalies = empty

    return alerts, port, anomalies


alerts, port, anomalies = load_summary()

# --- Top KPIs ---
col1, col2, col3, col4 = st.columns(4)
open_n = len(alerts) if alerts is not None and not alerts.empty else 0
crit = (
    int((alerts["severity"] == "CRITICAL").sum())
    if open_n and "severity" in alerts.columns
    else 0
)
cong = "—"
if port is not None and not port.empty and "congestion_index" in port.columns:
    try:
        cong = f"{float(port.iloc[0]['congestion_index']):.0f}"
    except Exception:
        cong = "—"
anom_n = len(anomalies) if anomalies is not None and not anomalies.empty else 0

col1.metric("Open alerts", open_n)
col2.metric("Critical", crit)
col3.metric("Port congestion idx", cong)
col4.metric("Recent anomalies", anom_n)

if open_n == 0 and anom_n == 0 and (port is None or port.empty):
    st.info(
        "Database connected, but core tables are empty or missing. "
        "Run on a machine with network access to Supabase:\n\n"
        "`python ingestion/init_operational_schema.py`\n"
        "`python ingestion/seed_cloud_demo.py`"
    )

st.subheader("Open alerts")
if alerts is not None and not alerts.empty:
    st.dataframe(
        alerts,
        width="stretch",
        hide_index=True,
    )
else:
    st.caption("No open alerts.")

st.subheader("Port metrics (recent)")
if port is not None and not port.empty:
    st.dataframe(port, width="stretch", hide_index=True)
else:
    st.caption("No port metrics.")

st.subheader("Ocean anomalies")
if anomalies is not None and not anomalies.empty:
    show_cols = [c for c in anomalies.columns if c in anomalies.columns]
    st.dataframe(anomalies[show_cols], width="stretch", hide_index=True)
else:
    st.caption("No anomaly rows.")

try:
    close_page()
except Exception:
    pass
