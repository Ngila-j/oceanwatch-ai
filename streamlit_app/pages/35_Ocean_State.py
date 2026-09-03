"""Phase 20 — Ocean State Engine UI."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Ocean State",
    page_icon=":material/water:",
    layout="wide",
)
st.title("Ocean State Engine")
st.caption(
    "Fused ocean state from SST · chlorophyll · bloom · habitat · climate risk — Kenya EEZ"
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
        "state": q(
            "SELECT * FROM fact_ocean_state ORDER BY as_of_date DESC LIMIT 5"
        ),
        "stress": q(
            "SELECT * FROM fact_ecological_stress ORDER BY as_of_date DESC LIMIT 5"
        ),
        "fish": q(
            "SELECT * FROM fact_fisheries_conditions ORDER BY as_of_date DESC LIMIT 5"
        ),
        "hazards": q(
            "SELECT * FROM fact_marine_hazards ORDER BY created_at DESC LIMIT 50"
        ),
    }


d = load()

if d["state"] is None or d["state"].empty or "error" in d["state"].columns:
    st.warning("No Phase 20 data. Run init_phase20_ocean_state.py and run_phase20_ocean_state.py")
    st.stop()

r = d["state"].iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Ocean state", r.get("ocean_state_score"), r.get("ocean_state_label"))
c2.metric("Ecology risk", r.get("ecology_risk"))
c3.metric("Fisheries condition", r.get("fisheries_condition_score"))
c4.metric("Confidence", r.get("confidence_score"))

c5, c6, c7 = st.columns(3)
c5.metric("SST °C", r.get("sst_celsius"))
c6.metric("CHL", r.get("chlorophyll_mg_m3"))
c7.metric("Freshness %", r.get("freshness_pct"))

st.caption(f"Drivers: {r.get('drivers')}")
st.caption(f"Model: {r.get('model_version')} · region={r.get('region_id')}")

st.subheader("Ocean state history (recent)")
st.dataframe(d["state"], width="stretch")

st.subheader("Ecological stress")
if d["stress"] is not None and not d["stress"].empty and "error" not in d["stress"].columns:
    s = d["stress"].iloc[0]
    st.metric("Stress", s.get("stress_score"), s.get("stress_level"))
    st.dataframe(d["stress"], width="stretch")
else:
    st.caption("No ecological stress rows")

st.subheader("Fisheries conditions")
if d["fish"] is not None and not d["fish"].empty and "error" not in d["fish"].columns:
    f = d["fish"].iloc[0]
    st.metric("Condition", f.get("condition_score"), f.get("condition_label"))
    st.dataframe(d["fish"], width="stretch")
else:
    st.caption("No fisheries condition rows")

st.subheader("Marine hazards")
if d["hazards"] is not None and not d["hazards"].empty and "error" not in d["hazards"].columns:
    st.dataframe(d["hazards"], width="stretch")
else:
    st.success("No marine hazards flagged for the current window")

st.info(
    "Scores are decision-support fusion products, not regulatory determinations. "
    "See Data Catalog for source licenses and lineage."
)