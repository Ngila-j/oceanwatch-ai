import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine, text

st.set_page_config(page_title="AIS Live", page_icon="📡", layout="wide")
st.title("📡 AIS Vessel Positions")
st.caption(
    "Kenya EEZ monitoring box — SAMPLE enrichment + live AISSTREAM when coverage allows"
)

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=120)
def load_ais():
    engine = create_engine(DB_URI, pool_pre_ping=True)
    try:
        summary = pd.read_sql(
            text(
                """
                SELECT source, COUNT(*) AS positions, COUNT(DISTINCT mmsi) AS vessels
                FROM fact_ais_positions
                GROUP BY source
                ORDER BY source
                """
            ),
            engine,
        )
        latest = pd.read_sql(
            text(
                """
                SELECT DISTINCT ON (mmsi) *
                FROM fact_ais_positions
                ORDER BY mmsi, event_time DESC
                """
            ),
            engine,
        )
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
| **SAMPLE** | Synthetic enrichment for demos, maps, and ML when live coverage is sparse |
| **AISSTREAM** | Real live AIS via AISStream.io (hybrid WORLD subscribe → Kenya/WIO filter) |

East Africa terrestrial AIS coverage is often thin. Empty live windows are expected; SAMPLE keeps the product usable.
"""
)

if summary.empty:
    st.warning("No AIS data. Run seed_ais_sample.py and/or fetch_ais_realtime.py")
else:
    st.subheader("Positions by source")
    st.dataframe(summary, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Total vessels (latest)",
        int(latest["mmsi"].nunique()) if not latest.empty else 0,
    )
    c2.metric(
        "SAMPLE rows",
        int(summary.loc[summary["source"] == "SAMPLE", "positions"].sum())
        if not summary.empty and (summary["source"] == "SAMPLE").any()
        else 0,
    )
    c3.metric(
        "AISSTREAM rows",
        int(summary.loc[summary["source"] == "AISSTREAM", "positions"].sum())
        if not summary.empty and (summary["source"] == "AISSTREAM").any()
        else 0,
    )

    if not latest.empty:
        # OpenStreetMap — free, no CARTO API key watermarks
        m = folium.Map(
            location=[-1.5, 42.0],
            zoom_start=6,
            tiles="OpenStreetMap",
        )
        folium.Rectangle(
            bounds=[[-6, 38], [3, 46]],
            color="blue",
            fill=True,
            fill_opacity=0.06,
            popup="Kenya / WIO monitoring box",
        ).add_to(m)

        for _, row in latest.iterrows():
            try:
                lat = float(row["latitude"])
                lon = float(row["longitude"])
            except (TypeError, ValueError, KeyError):
                continue
            color = "red" if str(row.get("source", "")).upper() == "AISSTREAM" else "green"
            name = row.get("vessel_name") or row.get("mmsi") or "vessel"
            popup = (
                f"<b>{name}</b><br>"
                f"{row.get('vessel_type')}<br>"
                f"Source: {row.get('source')}<br>"
                f"SOG: {row.get('sog')}<br>"
                f"{row.get('event_time')}"
            )
            folium.CircleMarker(
                location=[lat, lon],
                radius=5,
                color=color,
                fill=True,
                fill_opacity=0.8,
                popup=popup,
            ).add_to(m)

        st_folium(m, width=None, height=480, returned_objects=[])
        st.caption("Green = SAMPLE · Red = AISSTREAM (live)")

        st.subheader("Latest positions")
        cols = [
            c
            for c in [
                "event_time",
                "source",
                "vessel_name",
                "vessel_type",
                "latitude",
                "longitude",
                "sog",
            ]
            if c in latest.columns
        ]
        st.dataframe(latest[cols].head(50), use_container_width=True)