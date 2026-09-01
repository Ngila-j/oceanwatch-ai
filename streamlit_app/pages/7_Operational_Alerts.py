import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

from components.branding import attribution_footer, bandwidth_toggle

st.set_page_config(page_title="Operational Alerts", page_icon="🚨", layout="wide")
bandwidth_toggle()

st.title("Operational Alerts")
st.caption("What happened, why it matters — not legal determinations.")

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=60)
def load_alerts():
    eng = create_engine(DB_URI, pool_pre_ping=True)
    return pd.read_sql(
        text(
            """
            SELECT *
            FROM fact_alerts
            ORDER BY created_at DESC
            LIMIT 50
            """
        ),
        eng,
    )


df = load_alerts()
if df.empty:
    st.info("No alerts. Run anomaly engine + enrich_alerts.py")
else:
    for _, r in df.iterrows():
        sev = str(r.get("severity") or r.get("status") or "")
        with st.expander(f"{sev} · {r.get('title')} · {r.get('category')}"):
            st.write(r.get("message") or "")
            if "why_it_matters" in df.columns and pd.notna(r.get("why_it_matters")):
                st.markdown(f"**Why it matters:** {r.get('why_it_matters')}")
            else:
                # parse from message if embedded
                st.caption("See message text for context.")
            if "data_source" in df.columns and pd.notna(r.get("data_source")):
                st.caption(f"Source: {r.get('data_source')}")
            if "confidence_score" in df.columns and pd.notna(r.get("confidence_score")):
                st.caption(f"Confidence: {r.get('confidence_score')}")
            if "location_label" in df.columns and pd.notna(r.get("location_label")):
                st.caption(f"Where: {r.get('location_label')}")
            st.caption(f"When: {r.get('created_at')}")

attribution_footer()