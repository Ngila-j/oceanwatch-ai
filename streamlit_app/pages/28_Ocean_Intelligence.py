"""Phase 13 — Ocean Intelligence fusion dashboard (Kenya EEZ)."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Ocean Intelligence",
    page_icon=":material/tsunami:",
    layout="wide",
)
st.title("Ocean Intelligence")
st.caption(
    "Climate anomalies · bloom/habitat fusion · environmental early warning · Kenya EEZ"
)

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=45)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "fusion": q(
            "SELECT * FROM fact_ocean_risk_fusion ORDER BY as_of_date DESC LIMIT 5"
        ),
        "anom": q(
            "SELECT * FROM fact_ocean_climate_anomalies ORDER BY as_of_date DESC, metric"
        ),
        "warn": q(
            """
            SELECT * FROM fact_environmental_warnings
            WHERE status = 'OPEN'
            ORDER BY created_at DESC
            LIMIT 50
            """
        ),
        "hist": q(
            """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3
            FROM fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL
            ORDER BY date_key
            """
        ),
    }


d = load()

if d["fusion"] is None or d["fusion"].empty or "error" in d["fusion"].columns:
    st.warning("No fusion rows. Run init_phase13_ocean.py and run_phase13_ocean.py")
    if d["fusion"] is not None and not d["fusion"].empty and "error" in d["fusion"].columns:
        st.code(str(d["fusion"].iloc[0].get("error")))
    st.stop()

f = d["fusion"].iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Composite ocean risk",
    f.get("composite_ocean_risk"),
    str(f.get("risk_level")),
)
c2.metric("Climate risk", f.get("climate_risk_score"))
c3.metric("Bloom risk", f.get("bloom_risk_score"))
c4.metric("Habitat stress", f.get("habitat_stress_score"))
c5.metric("Confidence", f.get("confidence_score"))

if f.get("early_warning_flag"):
    st.error(f.get("early_warning_message") or "Early warning active")
else:
    st.success("No composite early warning at this time")

st.caption(
    f"Drivers: {f.get('drivers')} · Model: {f.get('model_version')} · "
    f"As of {f.get('as_of_date')}"
)

st.subheader("Climate anomalies")
if d["anom"] is not None and not d["anom"].empty and "error" not in d["anom"].columns:
    st.dataframe(d["anom"], width="stretch")
else:
    st.caption("No anomaly rows")

st.subheader("Environmental warnings")
if d["warn"] is not None and not d["warn"].empty and "error" not in d["warn"].columns:
    st.dataframe(d["warn"], width="stretch")
else:
    st.caption("No OPEN environmental warnings")

if d["hist"] is not None and not d["hist"].empty and "error" not in d["hist"].columns:
    st.subheader("SST history")
    fig = px.line(d["hist"], x="date_key", y="sst_celsius", markers=True)
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig, width="stretch")

    if d["hist"]["chlorophyll_mg_m3"].notna().any():
        st.subheader("Chlorophyll history")
        chl = d["hist"].dropna(subset=["chlorophyll_mg_m3"])
        fig2 = px.line(chl, x="date_key", y="chlorophyll_mg_m3", markers=True)
        fig2.update_layout(height=320, margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig2, width="stretch")

st.info("Decision-support only. Not an official ecological or health advisory.")