"""Anomaly Engine — elevated vessel / ops signals with evidence."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:
    def get_db_uri():
        import os
        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/oceanwatch_db"

st.set_page_config(page_title="Anomaly Engine", page_icon=":material/psychology:", layout="wide")

try:
    from ow_theme import apply_theme, init_a11y_defaults
    init_a11y_defaults(); apply_theme()
except Exception:
    pass
st.title("Anomaly Engine")
st.caption(
    "Behaviour and operational flags for human review. "
    "Not a legal determination of illegal activity."
)

DB = get_db_uri()
@st.cache_data(ttl=60)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "vessels": q(
            """
            SELECT vessel_name, vessel_type, risk_score, confidence_score, status, evidence
            FROM fact_vessel_anomalies
            ORDER BY risk_score DESC NULLS LAST
            LIMIT 50
            """
        ),
        "alerts": q(
            """
            SELECT category, severity, title, risk_score, evidence, status, created_at
            FROM fact_alerts
            WHERE status = 'OPEN'
              AND (
                UPPER(category) IN ('FISHING', 'PORT', 'ENVIRONMENT')
                OR UPPER(severity) IN ('ELEVATED', 'HIGH', 'CRITICAL')
              )
            ORDER BY risk_score DESC NULLS LAST
            LIMIT 40
            """
        ),
        "ocean_anom": q(
            """
            SELECT date_key, metric, current_value, anomaly_pct, severity
            FROM fact_ocean_anomalies
            ORDER BY created_at DESC NULLS LAST
            LIMIT 30
            """
        ),
    }


d = load()

st.subheader("Vessel behaviour scores")
v = d["vessels"]
if v is not None and not v.empty and "error" not in v.columns:
    st.dataframe(v, width="stretch")
else:
    st.caption("No vessel anomaly rows.")

st.subheader("Open elevated alerts")
a = d["alerts"]
if a is not None and not a.empty and "error" not in a.columns:
    st.dataframe(a, width="stretch")
else:
    st.caption("No matching open alerts.")

st.subheader("Ocean anomaly table")
o = d["ocean_anom"]
if o is not None and not o.empty and "error" not in o.columns:
    st.dataframe(o, width="stretch")
else:
    st.caption("No ocean anomaly rows (or table empty).")

st.info(
    "Always pair scores with evidence and primary data. "
    "Human review required before any enforcement-style interpretation."
)