import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine

st.set_page_config(page_title="AIS Live", page_icon="📡", layout="wide")
st.title("📡 AIS Vessel Positions")
st.caption("Sample AIS tracks inside the Kenya EEZ monitoring box (ready for real AIS / GFW feeds)")

@st.cache_data(ttl=120)
def load_ais():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        return pd.read_sql("""
            SELECT *
            FROM fact_ais_positions
            ORDER BY event_time DESC
            LIMIT 2000
        """, engine)
    except Exception as e:
        st.error(str(e))
        return pd.DataFrame()

df = load_ais()

if df.empty:
    st.warning("No AIS data. Run the AIS sample seed.")
    st.code("docker exec -it oceanwatch_airflow_web python /opt/airflow/ingestion/seed_ais_sample.py")
else:
    df["event_time"] = pd.to_datetime(df["event_time"])
    latest = df.sort_values("event_time").groupby("mmsi").tail(1)

    c1, c2, c3 = st.columns(3)
    c1.metric("Unique vessels", df["mmsi"].nunique())
    c2.metric("Positions loaded", len(df))
    c3.metric("Fishing vessels (latest)", len(latest[latest["vessel_type"] == "FISHING"]))

    m = folium.Map(location=[-1.5, 42.0], zoom_start=6, tiles="CartoDB positron")
    folium.Rectangle(bounds=[[-5, 39], [2, 45]], color="blue", fill=True, fill_opacity=0.08).add_to(m)

    color_map = {
        "FISHING": "red",
        "CARGO": "blue",
        "TANKER": "purple",
        "PASSENGER": "green",
        "OTHER": "gray"
    }

    for _, row in latest.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5,
            color=color_map.get(row["vessel_type"], "gray"),
            fill=True,
            fill_opacity=0.8,
            popup=f"{row['vessel_name']}<br>{row['vessel_type']}<br>SOG: {row['sog']} kn"
        ).add_to(m)

    st_folium(m, width=None, height=500, returned_objects=[])
    st.caption("Red = Fishing · Blue = Cargo · Purple = Tanker · Green = Passenger")

    st.subheader("Latest Positions")
    st.dataframe(
        latest[["event_time", "vessel_name", "vessel_type", "flag_country", "latitude", "longitude", "sog", "nav_status"]],
        use_container_width=True
    )