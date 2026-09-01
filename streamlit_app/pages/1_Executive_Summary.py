import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

st.set_page_config(page_title="Executive Summary", page_icon="ðŸ“Š", layout="wide")
st.title("ðŸ“Š OceanWatch Executive Summary")
st.caption(f"Last refreshed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")

@st.cache_data(ttl=120)
def load_summary():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    alerts = pd.read_sql("""
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
    """, engine)
    port = pd.read_sql("SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 1", engine)
    anomalies = pd.read_sql("SELECT * FROM fact_ocean_anomalies ORDER BY created_at DESC LIMIT 5", engine)
    return alerts, port, anomalies

alerts, port, anomalies = load_summary()

# --- Top KPIs ---
col1, col2, col3, col4 = st.columns(4)

elevated = len(alerts[alerts["severity"].isin(["CRITICAL", "ELEVATED"])]) if not alerts.empty else 0
col1.metric("Open High-Priority Alerts", elevated)

if not port.empty:
    m = port.iloc[0]
    col2.metric("Mombasa Congestion", m["congestion_level"])
    col3.metric("Active Vessels (Mombasa)", int(m["active_vessels"]))
    col4.metric("vs 30d Baseline", f"{m['vs_30d_baseline_pct']:+.1f}%")
else:
    col2.metric("Mombasa Congestion", "N/A")
    col3.metric("Active Vessels", "N/A")
    col4.metric("Baseline", "N/A")

st.divider()

# --- Priority Alerts ---
st.subheader("Priority Operational Alerts")
if alerts.empty:
    st.success("No open alerts.")
else:
    for _, row in alerts.iterrows():
        if row["severity"] in ("CRITICAL", "ELEVATED"):
            st.warning(f"**{row['title']}**  Â·  {row['category']}  Â·  Risk {row['risk_score']}")
        else:
            st.info(f"**{row['title']}**  Â·  {row['category']}")

# --- Coastal snapshot ---
st.subheader("Coastal Conditions Snapshot")
if not anomalies.empty:
    st.dataframe(
        anomalies[["date_key", "metric", "current_value", "mean_30d", "anomaly_pct", "severity"]],
        width="stretch"
    )
else:
    st.caption("No anomaly records yet.")