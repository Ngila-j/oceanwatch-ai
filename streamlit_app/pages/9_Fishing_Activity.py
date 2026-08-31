import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Fishing Activity", page_icon="🐟", layout="wide")
st.title("🐟 Fishing Activity Intelligence")
st.caption("Kenya EEZ · effort, behaviour flags, decision-support only")

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
        "gfw": q(
            """
            SELECT
                COUNT(*) AS cells,
                COALESCE(SUM(hours), 0) AS total_hours,
                COUNT(DISTINCT effort_date) AS days,
                MIN(effort_date) AS start_date,
                MAX(effort_date) AS end_date
            FROM fact_gfw_fishing_effort
            """
        ),
        "gfw_daily": q(
            """
            SELECT effort_date, SUM(hours) AS hours, COUNT(*) AS cells
            FROM fact_gfw_fishing_effort
            GROUP BY effort_date
            ORDER BY effort_date DESC
            LIMIT 14
            """
        ),
        "vessel": q(
            """
            SELECT vessel_name, vessel_type, risk_score, confidence_score, status, evidence
            FROM fact_vessel_anomalies
            ORDER BY risk_score DESC
            LIMIT 20
            """
        ),
        "alerts": q(
            """
            SELECT severity, title, description, created_at
            FROM fact_alerts
            WHERE status = 'OPEN'
              AND UPPER(COALESCE(category, '')) = 'FISHING'
            ORDER BY created_at DESC
            LIMIT 15
            """
        ),
    }


d = load()

st.subheader("GFW fishing effort (summary)")
g = d["gfw"]
if not g.empty and "error" not in g.columns:
    row = g.iloc[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Cells", int(row.get("cells") or 0))
    c2.metric("Total hours", round(float(row.get("total_hours") or 0), 1))
    c3.metric("Days", int(row.get("days") or 0))
    st.caption(
        f"Range: {row.get('start_date')} → {row.get('end_date')} · "
        "Powered by Global Fishing Watch — https://globalfishingwatch.org"
    )
else:
    st.warning("No GFW effort table/data yet.")

st.subheader("Recent daily effort")
gd = d["gfw_daily"]
if not gd.empty and "error" not in gd.columns:
    st.dataframe(gd, use_container_width=True)
else:
    st.caption("No daily effort rows.")

st.subheader("Vessel behaviour scores")
v = d["vessel"]
if not v.empty and "error" not in v.columns:
    st.dataframe(v, use_container_width=True)
else:
    st.caption("No vessel anomaly rows — run ml_vessel_anomaly.")

st.divider()
st.subheader("Open fishing-related alerts")
a = d["alerts"]
if not a.empty and "error" not in a.columns:
    st.dataframe(a, use_container_width=True)
else:
    st.caption("No open fishing alerts.")

st.info(
    "Not a legal or enforcement product. Anomalies mean unusual vs baseline. "
    "GFW use: attribution required; non-commercial where their licence applies."
)