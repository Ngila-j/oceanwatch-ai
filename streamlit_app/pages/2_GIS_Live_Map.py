import streamlit as st
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine
import pandas as pd

st.set_page_config(page_title="GIS Live Map", page_icon="🗺️", layout="wide")
st.title("🗺️ GIS Live Map – Western Indian Ocean / Mombasa")

@st.cache_data
def get_location():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    df = pd.read_sql("SELECT * FROM dim_location", engine)
    return df.iloc[0]

loc = get_location()

# Create map
m = folium.Map(
    location=[loc["centroid_lat"], loc["centroid_lon"]],
    zoom_start=6,
    tiles="CartoDB positron"
)

# Monitoring bounding box
folium.Rectangle(
    bounds=[
        [loc["min_latitude"], loc["min_longitude"]],
        [loc["max_latitude"], loc["max_longitude"]]
    ],
    color="#1E90FF",
    weight=2,
    fill=True,
    fill_color="#1E90FF",
    fill_opacity=0.12,
    popup="Oceanwatch Monitoring Area (Kenya EEZ focus)"
).add_to(m)

# Centroid
folium.CircleMarker(
    location=[loc["centroid_lat"], loc["centroid_lon"]],
    radius=8,
    color="red",
    fill=True,
    fill_color="red",
    popup="Region Centroid"
).add_to(m)

# Key locations
folium.Marker(
    location=[-4.0435, 39.6682],
    popup="<b>Mombasa Port</b><br>Major regional hub",
    tooltip="Mombasa Port",
    icon=folium.Icon(color="green", icon="ship", prefix="fa")
).add_to(m)

folium.Marker(
    location=[-1.2921, 36.8219],
    popup="Nairobi (reference)",
    icon=folium.Icon(color="gray", icon="info-sign")
).add_to(m)

# Layer control
folium.LayerControl().add_to(m)

st_folium(m, width=None, height=650, returned_objects=[])

st.markdown("""
**Map Legend**
- Blue rectangle → Current data ingestion bounding box  
- Red circle → Region centroid  
- Green ship → Mombasa Port  
""")