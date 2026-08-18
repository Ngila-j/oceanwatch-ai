import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine
import plotly.express as px

st.set_page_config(page_title="Fishing Activity", page_icon="🐟", layout="wide")
st.title("🐟 Fishing Activity Intelligence")
st.caption(
    "Sample AIS behaviour + Global Fishing Watch apparent fishing effort. "
    "GFW data powered by [Global Fishing Watch](https://globalfishingwatch.org)."
)

@st.cache_data(ttl=180)
def load():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    gfw = pd.DataFrame()
    sample = pd.DataFrame()
    try:
        gfw = pd.read_sql(
            "SELECT effort_date, lat, lon, hours, flag FROM fact_gfw_fishing_effort WHERE hours IS NOT NULL",
            engine,
        )
    except Exception:
        pass
    try:
        sample = pd.read_sql(
            "SELECT * FROM fact_fishing_activity LIMIT 500",
            engine,
        )
    except Exception:
        pass
    return gfw, sample


gfw, sample = load()

c1, c2, c3 = st.columns(3)
c1.metric("GFW effort cells", len(gfw))
c2.metric("GFW total hours", f"{gfw['hours'].sum():.1f}" if not gfw.empty else "0")
c3.metric("Sample fishing events", len(sample))

if not gfw.empty:
    st.subheader("GFW daily apparent fishing hours")
    daily = gfw.groupby("effort_date", as_index=False)["hours"].sum()
    st.plotly_chart(px.bar(daily, x="effort_date", y="hours"), use_container_width=True)

    st.subheader("GFW effort map")
    m = folium.Map(location=[-1.5, 42.0], zoom_start=6, tiles="CartoDB positron")
    folium.Rectangle(bounds=[[-5, 39], [2, 45]], color="blue", fill=True, fill_opacity=0.05).add_to(m)
    max_h = max(float(gfw["hours"].max()), 0.01)
    for _, row in gfw.iterrows():
        if pd.isna(row["lat"]) or pd.isna(row["lon"]):
            continue
        folium.CircleMarker(
            [row["lat"], row["lon"]],
            radius=3 + 10 * (float(row["hours"]) / max_h),
            color="#c0392b",
            fill=True,
            fill_opacity=0.65,
            popup=f"{row['effort_date']} · {row['hours']:.2f}h",
        ).add_to(m)
    st_folium(m, width=None, height=420, returned_objects=[])

st.page_link("pages/15_GFW_Fishing_Effort.py", label="Open full GFW Fishing Effort page →")

if not sample.empty:
    st.subheader("Sample / internal fishing activity table")
    st.dataframe(sample.head(50), use_container_width=True)

st.markdown("---")
st.caption("Apparent fishing effort is model-derived from AIS · not a legal determination of fishing.")