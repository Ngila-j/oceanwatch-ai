"""
Historical playback â€” simple day view for Kenya EEZ monitoring.
Decision-support only; coverage depends on ingested data.
"""

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Historical Playback", page_icon="âª", layout="wide")
st.title("Historical Playback")
st.caption(
    "Select a day and review available ocean, AIS, and index snapshots. "
    "Not a complete archive â€” only what OceanWatch has stored."
)

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_resource
def get_engine():
    return create_engine(DB_URI, pool_pre_ping=True)


def qdf(sql: str, params=None) -> pd.DataFrame:
    try:
        return pd.read_sql(text(sql), get_engine(), params=params or {})
    except Exception as e:
        st.warning(str(e))
        return pd.DataFrame()


# --- Date bounds from available data ---
bounds = qdf(
    """
    SELECT
        MIN(d)::date AS min_d,
        MAX(d)::date AS max_d
    FROM (
        SELECT date_key::date AS d FROM fact_ocean_conditions
        UNION ALL
        SELECT index_date::date FROM fact_wio_intelligence_index
        UNION ALL
        SELECT event_time::date FROM fact_ais_positions
        WHERE event_time IS NOT NULL
    ) x
    """
)

if bounds.empty or bounds.iloc[0]["min_d"] is None:
    st.warning("No dated data found. Run ingestion / compute jobs first.")
    st.stop()

min_d = pd.to_datetime(bounds.iloc[0]["min_d"]).date()
max_d = pd.to_datetime(bounds.iloc[0]["max_d"]).date()

selected = st.date_input(
    "Playback date",
    value=max_d,
    min_value=min_d,
    max_value=max_d,
)

st.markdown(f"### Snapshot for **{selected}**")

# --- Ocean conditions that day ---
ocean = qdf(
    """
    SELECT date_key, sst_celsius, chlorophyll_mg_m3, tide_mean_m, tide_min_m, tide_max_m
    FROM fact_ocean_conditions
    WHERE date_key::date = :d
    """,
    {"d": selected},
)

c1, c2, c3 = st.columns(3)
if not ocean.empty:
    row = ocean.iloc[0]
    c1.metric(
        "SST ( deg C)",
        f"{float(row['sst_celsius']):.2f}" if pd.notna(row.get("sst_celsius")) else "â€”",
    )
    c2.metric(
        "CHL",
        f"{float(row['chlorophyll_mg_m3']):.3f}"
        if pd.notna(row.get("chlorophyll_mg_m3"))
        else "â€”",
    )
    c3.metric(
        "Tide mean (m)",
        f"{float(row['tide_mean_m']):.2f}" if pd.notna(row.get("tide_mean_m")) else "â€”",
    )
else:
    st.info("No ocean conditions row for this date.")

# --- WIO-OII that day ---
idx = qdf(
    """
    SELECT overall_score, confidence_score, methodology_version, drivers,
           ocean_health_score, maritime_activity_score, fishing_pressure_score,
           port_risk_score, environmental_risk_score
    FROM fact_wio_intelligence_index
    WHERE index_date = :d
    """,
    {"d": selected},
)

if not idx.empty:
    i = idx.iloc[0]
    st.subheader("WIO-OII")
    a, b, c = st.columns(3)
    a.metric("Overall", f"{float(i['overall_score']):.1f}" if pd.notna(i.get("overall_score")) else "â€”")
    b.metric("Confidence", f"{float(i['confidence_score']):.0f}" if pd.notna(i.get("confidence_score")) else "â€”")
    c.metric("Method", str(i.get("methodology_version") or "â€”"))
    if i.get("drivers"):
        st.code(str(i["drivers"]), language=None)
else:
    st.caption("No WIO-OII row for this date (index is computed on run days).")

# --- AIS that day ---
ais = qdf(
    """
    SELECT mmsi, vessel_name, vessel_type, latitude, longitude, sog, source, event_time
    FROM fact_ais_positions
    WHERE event_time::date = :d
      AND latitude IS NOT NULL AND longitude IS NOT NULL
    ORDER BY event_time DESC
    LIMIT 300
    """,
    {"d": selected},
)

st.subheader("AIS positions that day")
if ais.empty:
    st.info("No AIS positions stored for this date.")
else:
    st.write(
        f"{len(ais)} positions Â· "
        f"{ais['mmsi'].nunique()} vessels Â· "
        f"sources: {', '.join(sorted(ais['source'].dropna().astype(str).unique()))}"
    )
    m = folium.Map(location=[-1.5, 42.0], zoom_start=6, tiles="OpenStreetMap")
    folium.Rectangle(
        bounds=[[-6, 38], [3, 46]],
        color="blue",
        fill=True,
        fill_opacity=0.05,
    ).add_to(m)
    for _, r in ais.iterrows():
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except Exception:
            continue
        color = "red" if str(r.get("source", "")).upper() == "AISSTREAM" else "green"
        folium.CircleMarker(
            [lat, lon],
            radius=4,
            color=color,
            fill=True,
            fill_opacity=0.75,
            popup=f"{r.get('vessel_name') or r.get('mmsi')}<br>{r.get('source')}<br>{r.get('event_time')}",
        ).add_to(m)
    st_folium(m, width=None, height=420, returned_objects=[])
    st.dataframe(
        ais[
            [
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
                if c in ais.columns
            ]
        ].head(50),
        width="stretch",
    )

# --- Alerts that day ---
alerts = qdf(
    """
    SELECT severity, category, title, description, created_at
    FROM fact_alerts
    WHERE created_at::date = :d OR detected_at::date = :d
    ORDER BY created_at DESC
    LIMIT 20
    """,
    {"d": selected},
)

st.subheader("Alerts that day")
if alerts.empty:
    st.caption("No alerts timestamped on this date.")
else:
    st.dataframe(alerts, width="stretch")

st.caption(
    "Playback shows stored snapshots only. Gaps mean data was not ingested for that day."
)
