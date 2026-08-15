import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import json

st.set_page_config(page_title="Operational Alerts", page_icon="🚨", layout="wide")
st.title("🚨 OceanWatch Alert Centre")
st.caption("Central operational alerts across Port, Fishing and Coastal domains")

@st.cache_data(ttl=120)
def load_alerts():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        return pd.read_sql("""
            SELECT alert_id, category, alert_type, severity, title, description,
                   risk_score, confidence_score, evidence, status, vessel_name,
                   location_label, created_at, detected_at
            FROM fact_alerts
            ORDER BY created_at DESC
            LIMIT 100
        """, engine)
    except Exception:
        return pd.DataFrame()

df = load_alerts()

if df.empty:
    st.info("No alerts yet. Run the operational intelligence engine.")
else:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Critical", len(df[df["severity"] == "CRITICAL"]))
    with c2:
        st.metric("Elevated", len(df[df["severity"] == "ELEVATED"]))
    with c3:
        st.metric("Watch", len(df[df["severity"] == "WATCH"]))
    with c4:
        st.metric("Open", len(df[df["status"] == "OPEN"]))

    st.subheader("Active Alerts")
    for _, row in df.iterrows():
        if row["severity"] == "CRITICAL":
            box = st.error
        elif row["severity"] == "ELEVATED":
            box = st.warning
        else:
            box = st.info

        header = f"**{row['title']}**  |  {row['category']}  |  Risk: {row['risk_score']}"
        if pd.notnull(row.get("vessel_name")):
            header += f"  |  Vessel: {row['vessel_name']}"
        box(header)
        st.caption(row["description"])
        if pd.notnull(row.get("evidence")):
            with st.expander("Evidence"):
                st.text(row["evidence"])

    st.subheader("Alert Log")
    st.dataframe(df[[
        "created_at", "category", "severity", "title", "risk_score",
        "confidence_score", "status", "vessel_name", "location_label"
    ]], use_container_width=True)