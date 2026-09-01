import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.set_page_config(page_title="Port Risk", page_icon="âš“", layout="wide")
st.title("Mombasa Port Operational Risk")

@st.cache_data(ttl=120)
def load():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    risk = pd.read_sql("SELECT * FROM fact_port_risk ORDER BY risk_date DESC LIMIT 5", engine)
    metrics = pd.read_sql("SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 1", engine)
    return risk, metrics

risk, metrics = load()

if risk.empty:
    st.warning("No port risk data. Run ml_port_risk.py")
else:
    r = risk.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Composite Risk", f"{r['composite_risk']:.1f}")
    c2.metric("Risk Level", r["risk_level"])
    c3.metric("Traffic Score", f"{r['traffic_score']:.1f}")
    c4.metric("Tide Score", f"{r['tide_score']:.1f}")

    if r["risk_level"] == "HIGH":
        st.error(f"**HIGH operational risk** â€” {r['drivers']}")
    elif r["risk_level"] == "MODERATE":
        st.warning(f"**MODERATE risk** â€” {r['drivers']}")
    else:
        st.success(f"**LOW risk** â€” {r['drivers']}")

    st.subheader("Score breakdown")
    st.dataframe(risk, width="stretch")

    if not metrics.empty:
        st.subheader("Latest port metrics")
        st.dataframe(metrics, width="stretch")
