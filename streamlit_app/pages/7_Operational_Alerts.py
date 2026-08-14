import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

st.set_page_config(page_title="Operational Alerts", page_icon="🚨", layout="wide")
st.title("🚨 Operational Alerts")

@st.cache_data(ttl=120)
def load_alerts():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        df = pd.read_sql("""
            SELECT alert_date, alert_type, severity, title, message, value, created_at
            FROM operational_alerts
            ORDER BY created_at DESC
            LIMIT 50
        """, engine)
        return df
    except Exception:
        return pd.DataFrame()

df = load_alerts()

if df.empty:
    st.info("No alerts generated yet. Run the full pipeline to produce alerts.")
else:
    # Summary counts
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Critical", len(df[df["severity"] == "CRITICAL"]))
    with col2:
        st.metric("Warnings", len(df[df["severity"] == "WARNING"]))
    with col3:
        st.metric("Info", len(df[df["severity"] == "INFO"]))

    st.subheader("Recent Alerts")

    for _, row in df.iterrows():
        if row["severity"] == "CRITICAL":
            st.error(f"**{row['title']}** — {row['message']}")
        elif row["severity"] == "WARNING":
            st.warning(f"**{row['title']}** — {row['message']}")
        else:
            st.info(f"**{row['title']}** — {row['message']}")

    st.subheader("Alert Log")
    st.dataframe(df, use_container_width=True)