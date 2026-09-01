import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine
import plotly.express as px

st.set_page_config(page_title="GFW Fishing Effort", page_icon="ðŸŽ£", layout="wide")
st.title("Apparent Fishing Effort (Global Fishing Watch)")

st.caption(
    "Fishing effort data powered by [Global Fishing Watch](https://globalfishingwatch.org). "
    "Non-commercial use Â· CC BY-NC 4.0 Â· Apparent fishing effort from AIS-based models."
)

@st.cache_data(ttl=180)
def load_gfw():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        return pd.read_sql(
            """
            SELECT effort_date, lat, lon, hours, flag, vessel_ids, source, loaded_at
            FROM fact_gfw_fishing_effort
            WHERE hours IS NOT NULL
            ORDER BY effort_date, hours DESC
            """,
            engine,
        )
    except Exception as e:
        st.error(f"Could not load GFW table: {e}")
        return pd.DataFrame()

df = load_gfw()

if df.empty:
    st.warning("No GFW data yet. Run fetch_gfw_fishing_effort.py inside Airflow.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Effort cells", len(df))
c2.metric("Total hours", f"{df['hours'].sum():.1f}")
c3.metric("Days covered", df["effort_date"].nunique())
c4.metric("Flags", int(df["flag"].nunique()) if "flag" in df.columns and df["flag"].notna().any() else 0)

st.subheader("Daily fishing hours (Kenya monitoring box)")
daily = df.groupby("effort_date", as_index=False)["hours"].sum()
fig = px.bar(daily, x="effort_date", y="hours", labels={"hours": "Apparent fishing hours"})
st.plotly_chart(fig, width="stretch")

st.subheader("Spatial effort map")
m = folium.Map(location=[-1.5, 42.0], zoom_start=6, tiles="CartoDB positron")
folium.Rectangle(bounds=[[-5, 39], [2, 45]], color="blue", fill=True, fill_opacity=0.05).add_to(m)

max_h = max(float(df["hours"].max()), 0.01)
for _, row in df.iterrows():
    if pd.isna(row["lat"]) or pd.isna(row["lon"]):
        continue
    radius = 3 + 12 * (float(row["hours"]) / max_h)
    folium.CircleMarker(
        location=[row["lat"], row["lon"]],
        radius=radius,
        color="#c0392b",
        fill=True,
        fill_opacity=0.6,
        popup=f"Date: {row['effort_date']}<br>Hours: {row['hours']:.2f}<br>Flag: {row.get('flag')}",
    ).add_to(m)

st_folium(m, width=None, height=480, returned_objects=[])

st.subheader("Top cells")
st.dataframe(df.sort_values("hours", ascending=False).head(30), width="stretch")

st.markdown("---")
st.markdown(
    """
**Attribution**  
Global Fishing Watch Â· 4Wings API (`public-global-fishing-effort:latest`)  
[https://globalfishingwatch.org/our-apis/](https://globalfishingwatch.org/our-apis/)

Apparent fishing effort is model-derived from AIS and is not a legal determination of fishing activity.
"""
)
