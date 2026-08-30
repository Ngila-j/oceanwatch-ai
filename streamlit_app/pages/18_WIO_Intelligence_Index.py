"""
WIO Ocean Intelligence Index — Kenya EEZ
Matches fact_wio_intelligence_index columns.
"""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

from components.branding import attribution_footer, bandwidth_toggle, is_low_bandwidth

st.set_page_config(page_title="WIO-OII", page_icon="📊", layout="wide")
bandwidth_toggle()

st.title("📊 WIO Ocean Intelligence Index")
st.caption("Kenya EEZ signature index — history builds as daily runs accumulate.")

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=60)
def load_index() -> pd.DataFrame:
    eng = create_engine(DB_URI, pool_pre_ping=True)
    return pd.read_sql(
        text(
            """
            SELECT
                index_date,
                region_id,
                ocean_health_score,
                maritime_activity_score,
                fishing_pressure_score,
                port_risk_score,
                environmental_risk_score,
                overall_score,
                confidence_score,
                drivers,
                methodology_version,
                created_at
            FROM fact_wio_intelligence_index
            ORDER BY index_date DESC
            """
        ),
        eng,
    )


try:
    df = load_index()
except Exception as e:
    st.error(f"Could not load index: {e}")
    st.info("Run: docker exec -it oceanwatch_airflow_web python /opt/airflow/ingestion/compute_wio_index.py")
    st.stop()

if df.empty:
    st.warning("No index rows yet. Run compute_wio_index.py first.")
    st.stop()

latest = df.iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall", f"{float(latest.get('overall_score') or 0):.1f}")
c2.metric("Confidence", f"{float(latest.get('confidence_score') or 0):.1f}")
c3.metric("As of", str(latest.get("index_date")))
c4.metric("Method", str(latest.get("methodology_version") or "—"))

st.write(f"Region: **{latest.get('region_id')}**")
st.code(str(latest.get("drivers") or ""), language=None)

st.subheader("Latest components")
comp = {}
mapping = [
    ("Ocean health", "ocean_health_score"),
    ("Maritime activity", "maritime_activity_score"),
    ("Fishing pressure", "fishing_pressure_score"),
    ("Port risk (raw)", "port_risk_score"),
    ("Environmental risk (raw)", "environmental_risk_score"),
]
for label, col in mapping:
    if col in df.columns and pd.notna(latest.get(col)):
        comp[label] = float(latest[col])

if comp:
    if is_low_bandwidth():
        st.dataframe(pd.DataFrame({"component": list(comp.keys()), "score": list(comp.values())}))
    else:
        st.bar_chart(pd.Series(comp))
else:
    st.caption("No component scores available.")

st.subheader("History")
window = st.selectbox("Window", ["All", "7 days", "30 days"], index=0)
hist = df.copy()
hist["index_date"] = pd.to_datetime(hist["index_date"])

if window == "7 days":
    hist = hist[hist["index_date"] >= hist["index_date"].max() - pd.Timedelta(days=7)]
elif window == "30 days":
    hist = hist[hist["index_date"] >= hist["index_date"].max() - pd.Timedelta(days=30)]

hist = hist.sort_values("index_date")
plot_cols = [c for c in ["overall_score", "ocean_health_score", "maritime_activity_score"] if c in hist.columns]

if is_low_bandwidth():
    st.dataframe(hist, use_container_width=True)
else:
    if plot_cols:
        st.line_chart(hist.set_index("index_date")[plot_cols])
    st.dataframe(hist, use_container_width=True)

st.caption(
    "Prototype decision-support index — not an official government statistic. "
    "Port and environmental scores are risk-style (higher can mean more stress)."
)
attribution_footer()