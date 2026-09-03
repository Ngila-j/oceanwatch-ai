"""Phase 15 — Fisheries Intelligence (Kenya EEZ)."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Fisheries Intelligence",
    page_icon=":material/phishing:",
    layout="wide",
)
st.title("Fisheries Intelligence")
st.caption(
    "Effort · hotspots · seasonality · activity risk heuristics · Kenya EEZ · "
    "Not a legal finding of illegal fishing"
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
        "risk": q(
            "SELECT * FROM fact_illegal_fishing_risk ORDER BY as_of_date DESC LIMIT 1"
        ),
        "hot": q(
            "SELECT * FROM fact_fishing_hotspots ORDER BY hotspot_rank LIMIT 20"
        ),
        "season": q(
            "SELECT * FROM fact_fisheries_seasonality ORDER BY month_num"
        ),
        "alerts": q(
            """
            SELECT * FROM fact_fisheries_alerts
            WHERE status = 'OPEN'
            ORDER BY created_at DESC LIMIT 50
            """
        ),
        "grid": q(
            """
            SELECT lat, lon, SUM(hours) AS hours
            FROM fact_fishing_effort_grid
            WHERE lat IS NOT NULL AND lon IS NOT NULL
            GROUP BY lat, lon
            """
        ),
    }


d = load()

if d["risk"] is None or d["risk"].empty or "error" in d["risk"].columns:
    st.warning("No Phase 15 data. Run init_phase15_fisheries.py and run_phase15_fisheries.py")
    st.stop()

r = d["risk"].iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Activity risk", r.get("risk_score"), str(r.get("risk_level")))
c2.metric("GFW hours", r.get("gfw_hours"))
c3.metric("Hotspot intensity", r.get("hotspot_intensity"))
c4.metric("Confidence", r.get("confidence_score"))

st.caption(f"Drivers: {r.get('drivers')}")
st.info(r.get("disclaimer") or "Heuristic only — not a legal determination.")

st.subheader("Fisheries alerts")
if d["alerts"] is not None and not d["alerts"].empty and "error" not in d["alerts"].columns:
    st.dataframe(d["alerts"], width="stretch")
else:
    st.caption("No OPEN fisheries alerts")

st.subheader("Hotspots")
if d["hot"] is not None and not d["hot"].empty and "error" not in d["hot"].columns:
    st.dataframe(d["hot"], width="stretch")
else:
    st.caption("No hotspots")

st.subheader("Seasonal patterns")
if d["season"] is not None and not d["season"].empty and "error" not in d["season"].columns:
    st.dataframe(d["season"], width="stretch")
    fig = px.bar(d["season"], x="month_name", y="total_hours", title="Effort hours by month")
    st.plotly_chart(fig, width="stretch")
else:
    st.caption("No seasonality rows (need multi-month GFW history)")

st.subheader("Effort heatmap (grid cells)")
if d["grid"] is not None and not d["grid"].empty and "error" not in d["grid"].columns:
    fig = px.scatter(
        d["grid"],
        x="lon",
        y="lat",
        size="hours",
        color="hours",
        title="GFW effort cells",
        color_continuous_scale="YlOrRd",
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, width="stretch")
else:
    st.caption("No geocoded grid cells — table may still hold hours without lat/lon")

st.caption("Fishing effort powered by Global Fishing Watch where sourced from GFW extracts.")