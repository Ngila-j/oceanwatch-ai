"""Phase 21 — Unified Risk Engine UI."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Unified Risk",
    page_icon=":material/shield:",
    layout="wide",
)
st.title("OceanWatch Risk Engine")
st.caption(
    "Composite risk with domain scores, driver contributions, confidence and freshness"
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
        "composite": q(
            "SELECT * FROM fact_unified_risk_composite ORDER BY as_of_date DESC LIMIT 5"
        ),
        "domains": q(
            "SELECT * FROM fact_unified_risk ORDER BY as_of_date DESC, domain"
        ),
        "drivers": q(
            "SELECT * FROM fact_unified_risk_drivers ORDER BY contribution DESC"
        ),
    }


d = load()

if d["composite"] is None or d["composite"].empty or "error" in d["composite"].columns:
    st.warning("No Phase 21 data. Run init_phase21_risk.py and run_phase21_risk_engine.py")
    st.stop()

r = d["composite"].iloc[0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Composite risk", r.get("composite_score"), r.get("composite_level"))
c2.metric("Confidence", r.get("confidence_score"))
c3.metric("Freshness %", r.get("freshness_pct"))
c4.metric("Data sources", r.get("data_sources_count"))

st.markdown(f"**Model:** {r.get('model_name')} · `{r.get('model_version')}`")
st.caption(f"Drivers: {r.get('drivers')}")
st.caption(f"Region: {r.get('region_id')} · {r.get('country_id')} · as of {r.get('as_of_date')}")

st.subheader("Domain scores")
if d["domains"] is not None and not d["domains"].empty and "error" not in d["domains"].columns:
    latest = d["domains"]
    if "as_of_date" in latest.columns:
        latest = latest[latest["as_of_date"] == latest["as_of_date"].max()]
    st.dataframe(latest, width="stretch")
    fig = px.bar(
        latest,
        x="domain",
        y="risk_score",
        color="risk_level",
        title="Domain risk scores",
        text="risk_score",
    )
    st.plotly_chart(fig, width="stretch")
else:
    st.caption("No domain rows")

st.subheader("Driver contributions")
if d["drivers"] is not None and not d["drivers"].empty and "error" not in d["drivers"].columns:
    st.dataframe(d["drivers"], width="stretch")
    fig2 = px.bar(
        d["drivers"],
        x="contribution",
        y="driver_name",
        color="domain",
        orientation="h",
        title="Driver contributions",
    )
    st.plotly_chart(fig2, width="stretch")
else:
    st.caption("No driver rows")

st.subheader("Truth layer")
st.markdown(
    f"""
| Field | Value |
|-------|-------|
| **VALUE** | {r.get('composite_score')} |
| **STATUS** | {r.get('composite_level')} |
| **CONFIDENCE** | {r.get('confidence_score')}% |
| **FRESHNESS** | {r.get('freshness_pct')}% |
| **SOURCES** | {r.get('data_sources_count')} |
| **MODEL** | {r.get('model_name')} ({r.get('model_version')}) |
"""
)

st.info(
    "Composite risk is decision support only. Fisheries domain uses activity heuristics, "
    "not legal determinations. See Data Catalog for lineage and licenses."
)