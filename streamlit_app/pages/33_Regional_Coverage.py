"""Phase 18 — Regional coverage hierarchy."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Regional Coverage",
    page_icon=":material/public:",
    layout="wide",
)
st.title("Regional Coverage")
st.caption(
    "Western Indian Ocean hierarchy — Kenya ACTIVE; peers PLANNED. "
    "One pipeline design, filter by country_id / region_id."
)

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
        "countries": q("SELECT * FROM dim_countries ORDER BY country_id"),
        "regions": q("SELECT * FROM dim_regions ORDER BY country_id, region_id"),
        "ports": q("SELECT * FROM dim_ports_ref ORDER BY country_id, port_id"),
        "zones": q("SELECT * FROM dim_marine_zones ORDER BY country_id, zone_id"),
    }


d = load()

if d["regions"] is None or d["regions"].empty or "error" in d["regions"].columns:
    st.warning("No Phase 18 data. Run init_phase18_regions.py and run_phase18_regions.py")
    st.stop()

active_r = (d["regions"]["status"] == "ACTIVE").sum()
planned_r = (d["regions"]["status"] == "PLANNED").sum()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Countries", len(d["countries"]))
c2.metric("Regions", len(d["regions"]))
c3.metric("ACTIVE regions", int(active_r))
c4.metric("PLANNED regions", int(planned_r))

st.subheader("Countries")
st.dataframe(d["countries"], width="stretch")

st.subheader("Regions")
st.dataframe(d["regions"], width="stretch")

# Bounding-box centres for a simple map view
reg = d["regions"].copy()
reg["centroid_lat"] = (reg["min_lat"] + reg["max_lat"]) / 2
reg["centroid_lon"] = (reg["min_lon"] + reg["max_lon"]) / 2
fig = px.scatter(
    reg,
    x="centroid_lon",
    y="centroid_lat",
    color="status",
    hover_name="region_name",
    hover_data=["country_id", "region_type", "region_id"],
    title="Region centroids (boxes not drawn as polygons)",
)
fig.update_yaxes(scaleanchor="x", scaleratio=1)
st.plotly_chart(fig, width="stretch")

st.subheader("Ports")
st.dataframe(d["ports"], width="stretch")

st.subheader("Marine zones")
st.dataframe(d["zones"], width="stretch")

st.info(
    "Official EEZ/MPA polygons are not digitized here. "
    "Coordinates are operational monitoring boxes for pipeline filtering."
)