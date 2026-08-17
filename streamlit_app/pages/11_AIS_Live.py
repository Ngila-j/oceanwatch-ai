import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine

st.set_page_config(page_title="AIS Live", page_icon="📡", layout="wide")
st.title("📡 AIS Vessel Positions")
st.caption("Kenya EEZ monitoring box — SAMPLE enrichment + live AISSTREAM when coverage allows")

@st.cache_data(ttl=120)
def load_ais():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    try:
        summary = pd.read_sql("""
            SELECT source, COUNT(*) AS positions, COUNT(DISTINCT mmsi) AS vessels
            FROM fact_ais_positions
            GROUP BY source
            ORDER BY source
        """, engine)
        latest = pd.read_sql("""
            SELECT DISTINCT ON (mmsi) *
            FROM fact_ais_positions
            ORDER BY mmsi, event_time DESC
        """, engine)
        return summary, latest
    except Exception as e:
        st.error(str(e))
        return pd.DataFrame(), pd.DataFrame()

summary, latest = load_ais()

st.info(
    """
**Data sources**

| Source | Meaning |
|--------|---------|
| **SAMPLE** | Synthetic enrichment for continuous demos, maps, and ML when live coverage is sparse |
| **AISSTREAM** | Real live AIS via AISStream.io (hybrid WORLD subscribe → Kenya/WIO client filter) |

East Africa terrestrial AIS coverage is often thin. Empty live windows are expected; SAMPLE keeps the product usable.
"""
)

if summary.empty:
    st.warning("No AIS data. Run seed_ais_sample.py and/or fetch_ais_realtime.py")
else:
    st.subheader("Positions by source")
    st.dataframe(summary, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("Total vessels (latest)", latest["mmsi"].nunique() if not latest.empty else 0)
    c2.metric("SAMPLE rows", int(summary.loc[summary["source"] == "SAMPLE", "positions"].sum()) if "SAMPLE" in summary["source"].values else 0)
    c3.metric("AISSTREAM rows", int(summary.loc[summary["source"] == "AISSTREAM", "positions"].sum()) if "AISSTREAM" in summary["source"].values else 0)

    if not latest.empty:
        m = folium.Map(location=[-1.5, 42.0], zoom_start=6, tiles="CartoDB positron")
        folium.Rectangle(bounds=[[-6, 38], [3, 46]], color="blue", fill=True, fill_opacity=0.06).add_to(m)

        for _, row in latest.iterrows():
            color = "red" if row.get("source") == "AISSTREAM" else "green"
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]],
                radius=5,
                color=color,
                fill=True,
                fill_opacity=0.8,
                popup=f"{row.get('vessel_name')}<br>{row.get('vessel_type')}<br>{row.get('source')}",
            ).add_to(m)

        st_folium(m, width=None, height=480, returned_objects=[])
        st.caption("Green = SAMPLE · Red = AISSTREAM (live)")

        st.subheader("Latest positions")
        st.dataframe(
            latest[["event_time", "source", "vessel_name", "vessel_type", "latitude", "longitude", "sog"]].head(50),
            use_container_width=True,
        )