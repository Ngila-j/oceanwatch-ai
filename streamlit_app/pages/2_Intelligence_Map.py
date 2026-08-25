"""
OceanWatch Intelligence Map — Kenya EEZ layered map (Priority 1).
"""

import folium
import pandas as pd
import streamlit as st
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from sqlalchemy import create_engine, text

from components.branding import attribution_footer, bandwidth_toggle, is_low_bandwidth

st.set_page_config(page_title="Intelligence Map", page_icon="🗺️", layout="wide")
bandwidth_toggle()

st.title("🗺️ OceanWatch Intelligence Map")
st.caption("Kenya EEZ / Mombasa — toggle layers. Decision-support only.")

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"

MIN_LON, MAX_LON = 39.0, 45.0
MIN_LAT, MAX_LAT = -5.0, 2.0
CENTER = [-1.5, 42.0]
MOMBASA = [-4.0435, 39.6682]


@st.cache_resource
def get_engine():
    return create_engine(DB_URI, pool_pre_ping=True)


def qdf(sql: str, params=None) -> pd.DataFrame:
    try:
        return pd.read_sql(text(sql), get_engine(), params=params or {})
    except Exception as e:
        st.warning(f"Query skipped: {e}")
        return pd.DataFrame()


def table_columns(table: str) -> set:
    df = qdf(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :t
        """,
        {"t": table},
    )
    if df.empty:
        return set()
    return set(df["column_name"].str.lower().tolist())


def pick(cols: set, candidates):
    for c in candidates:
        if c.lower() in cols:
            # return actual name from DB (case)
            for real in cols:
                if real == c.lower():
                    return real
    return None


st.sidebar.markdown("### Layers")
show_eez = st.sidebar.checkbox("Kenya monitoring box", True)
show_mombasa = st.sidebar.checkbox("Mombasa port marker", True)
show_sst = st.sidebar.checkbox("SST summary marker", True)
show_chl = st.sidebar.checkbox("Chlorophyll summary marker", False)
show_ais = st.sidebar.checkbox("AIS vessels", True)
show_gfw = st.sidebar.checkbox("GFW fishing effort cells", True)
show_alerts = st.sidebar.checkbox("Alert markers", False)

max_ais = st.sidebar.slider("Max AIS points", 50, 500, 200, 50)
max_gfw = st.sidebar.slider("Max GFW cells", 20, 200, 80, 20)

if is_low_bandwidth():
    st.info("Low-bandwidth mode: fewer points recommended.")
    max_ais = min(max_ais, 100)
    max_gfw = min(max_gfw, 40)

sst = qdf(
    """
    SELECT date_key, sst_celsius, chlorophyll_mg_m3
    FROM fact_ocean_conditions
    WHERE sst_celsius IS NOT NULL
    ORDER BY date_key DESC
    LIMIT 1
    """
)

ocean_note = None
if not sst.empty:
    ocean_note = (
        f"Latest SST mean (region product): {float(sst.iloc[0]['sst_celsius']):.2f} °C "
        f"on {sst.iloc[0]['date_key']}"
    )

ais = qdf(
    f"""
    SELECT mmsi, vessel_name, vessel_type, latitude, longitude, sog, nav_status, event_time, source
    FROM fact_ais_positions
    WHERE latitude BETWEEN {MIN_LAT} AND {MAX_LAT}
      AND longitude BETWEEN {MIN_LON} AND {MAX_LON}
    ORDER BY event_time DESC NULLS LAST
    LIMIT {int(max_ais)}
    """
)

# --- GFW: discover columns ---
gfw_cols = table_columns("fact_gfw_fishing_effort")
gfw = pd.DataFrame()
if gfw_cols:
    lat_c = pick(
        gfw_cols,
        ["latitude", "lat", "cell_lat", "grid_lat", "y"],
    )
    lon_c = pick(
        gfw_cols,
        ["longitude", "lon", "lng", "cell_lon", "grid_lon", "x"],
    )
    hrs_c = pick(gfw_cols, ["hours", "fishing_hours", "effort_hours", "hour"])
    date_c = pick(gfw_cols, ["effort_date", "date", "day", "time"])

    # re-fetch real column names with original case from information_schema
    col_df = qdf(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'fact_gfw_fishing_effort'
        """
    )
    real = {c.lower(): c for c in col_df["column_name"].tolist()} if not col_df.empty else {}

    def R(name):
        return real.get(name, name) if name else None

    lat_c, lon_c, hrs_c, date_c = R(lat_c), R(lon_c), R(hrs_c), R(date_c)

    if lat_c and lon_c:
        select_bits = [f'"{lat_c}" AS latitude', f'"{lon_c}" AS longitude']
        if hrs_c:
            select_bits.append(f'"{hrs_c}" AS hours')
        if date_c:
            select_bits.append(f'"{date_c}" AS effort_date')
        sql = f"""
            SELECT {", ".join(select_bits)}
            FROM fact_gfw_fishing_effort
            WHERE "{lat_c}" IS NOT NULL AND "{lon_c}" IS NOT NULL
            ORDER BY 1 DESC
            LIMIT {int(max_gfw)}
        """
        gfw = qdf(sql)
    else:
        st.caption(
            f"GFW has no lat/lon-like columns. Found: {sorted(gfw_cols)}. "
            "Layer disabled until coordinates exist."
        )
else:
    st.caption("Table fact_gfw_fishing_effort not found.")

alerts = qdf(
    """
    SELECT category, severity, title, created_at
    FROM fact_alerts
    ORDER BY created_at DESC
    LIMIT 10
    """
)

if ocean_note:
    st.success(ocean_note)

m = folium.Map(location=CENTER, zoom_start=6, tiles="OpenStreetMap")

if show_eez:
    folium.Rectangle(
        bounds=[[MIN_LAT, MIN_LON], [MAX_LAT, MAX_LON]],
        color="#1368ce",
        weight=2,
        fill=True,
        fill_opacity=0.05,
        popup="OceanWatch Kenya monitoring box",
    ).add_to(m)

if show_mombasa:
    folium.Marker(
        MOMBASA,
        popup="Mombasa Port",
        tooltip="Mombasa",
        icon=folium.Icon(color="red", icon="info-sign"),
    ).add_to(m)

if show_sst and not sst.empty:
    folium.CircleMarker(
        location=CENTER,
        radius=12,
        color="#e67e22",
        fill=True,
        fill_opacity=0.7,
        popup=ocean_note or "SST",
        tooltip="Regional SST product (summary)",
    ).add_to(m)

if show_chl and not sst.empty and pd.notna(sst.iloc[0].get("chlorophyll_mg_m3")):
    folium.CircleMarker(
        location=[CENTER[0] + 0.3, CENTER[1] + 0.3],
        radius=10,
        color="#27ae60",
        fill=True,
        fill_opacity=0.6,
        popup=f"CHL≈{float(sst.iloc[0]['chlorophyll_mg_m3']):.3f}",
        tooltip="Regional CHL product (summary)",
    ).add_to(m)

if show_ais and not ais.empty:
    cluster = MarkerCluster(name="AIS").add_to(m)
    for _, r in ais.iterrows():
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except Exception:
            continue
        name = r.get("vessel_name") or r.get("mmsi") or "vessel"
        popup = (
            f"<b>{name}</b><br>Type: {r.get('vessel_type')}<br>"
            f"SOG: {r.get('sog')}<br>Source: {r.get('source')}<br>"
            f"Time: {r.get('event_time')}"
        )
        folium.CircleMarker(
            [lat, lon],
            radius=4,
            color="#2980b9",
            fill=True,
            fill_opacity=0.8,
            popup=popup,
        ).add_to(cluster)

if show_gfw and not gfw.empty and "latitude" in gfw.columns and "longitude" in gfw.columns:
    for _, r in gfw.iterrows():
        try:
            lat, lon = float(r["latitude"]), float(r["longitude"])
        except Exception:
            continue
        hrs = r["hours"] if "hours" in gfw.columns else ""
        ed = r["effort_date"] if "effort_date" in gfw.columns else ""
        folium.CircleMarker(
            [lat, lon],
            radius=5,
            color="#8e44ad",
            fill=True,
            fill_opacity=0.5,
            popup=f"GFW hours: {hrs}<br>date: {ed}",
            tooltip="GFW fishing effort",
        ).add_to(m)

if show_alerts and not alerts.empty:
    for i, (_, r) in enumerate(alerts.head(5).iterrows()):
        folium.Marker(
            [MOMBASA[0] + 0.05 * (i % 5), MOMBASA[1] + 0.05 * (i % 3)],
            icon=folium.Icon(color="orange", icon="info-sign"),
            popup=f"{r.get('severity')}: {r.get('title')}<br>{r.get('category')}",
        ).add_to(m)

st_folium(m, width=None, height=420 if is_low_bandwidth() else 560, returned_objects=[])

with st.expander("Legend & limits"):
    st.markdown(
        """
- **Blue box** — monitoring bbox  
- **AIS** — vessel positions  
- **Purple** — GFW cells when coordinates exist  
- SST/CHL markers are **regional summary products**, not full rasters yet  
"""
    )

st.caption(
    "Fishing effort powered by Global Fishing Watch — https://globalfishingwatch.org"
)
attribution_footer()