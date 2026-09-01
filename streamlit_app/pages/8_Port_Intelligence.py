import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Port Intelligence", page_icon="âš“", layout="wide")
st.title("Mombasa Port Intelligence")
st.caption("Operational snapshot Â· Kenya-first Â· decision-support only")

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"

@st.cache_data(ttl=60)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "metrics": q(
            "SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 14"
        ),
        "risk": q("SELECT * FROM fact_port_risk ORDER BY risk_date DESC LIMIT 7"),
        "alerts": q(
            """
            SELECT severity, title, description, created_at
            FROM fact_alerts
            WHERE status = 'OPEN' AND UPPER(COALESCE(category, '')) = 'PORT'
            ORDER BY created_at DESC
            LIMIT 10
            """
        ),
    }

d = load()
m, r, a = d["metrics"], d["risk"], d["alerts"]

if not m.empty and "error" not in m.columns:
    latest = m.iloc[0]
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Active vessels", latest.get("active_vessels", "â€”"))
    c2.metric("Arrivals", latest.get("arrivals", "â€”"))
    c3.metric("Departures", latest.get("departures", "â€”"))
    c4.metric("Congestion", str(latest.get("congestion_level", "â€”")))
    c5.metric("Vs 30d baseline %", latest.get("vs_30d_baseline_pct", "â€”"))
    st.subheader("Recent port metrics")
    st.dataframe(m, width="stretch")
else:
    st.warning("No fact_port_metrics â€” run operational intelligence / DAG.")

st.subheader("Port operational risk")
if not r.empty and "error" not in r.columns:
    st.dataframe(r, width="stretch")
else:
    st.info("No fact_port_risk rows yet.")

st.subheader("Open port alerts")
st.dataframe(a if not a.empty else pd.DataFrame({"note": ["None open"]}), width="stretch")

st.info(
    "Not official Kenya Ports Authority data. Prototype metrics for planning awareness only."
)
