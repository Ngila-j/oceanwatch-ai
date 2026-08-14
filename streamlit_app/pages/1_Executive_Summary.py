import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

st.set_page_config(page_title="Executive Summary", page_icon="📊", layout="wide")
st.title("📊 Executive Summary")
st.caption(f"Last refreshed: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC")

@st.cache_data(ttl=300)
def load_latest_conditions():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    df = pd.read_sql("""
        SELECT date_key, sst_celsius, chlorophyll_mg_m3,
               tide_mean_m, tide_min_m, tide_max_m, tide_obs_count
        FROM fact_ocean_conditions
        ORDER BY date_key DESC
    """, engine)
    return df

df = load_latest_conditions()

if df.empty:
    st.warning("No data available yet. Run the Airflow pipeline first.")
else:
    # Latest non-null values
    latest_sst = df["sst_celsius"].dropna().iloc[0] if not df["sst_celsius"].dropna().empty else None
    latest_chl = df["chlorophyll_mg_m3"].dropna().iloc[0] if not df["chlorophyll_mg_m3"].dropna().empty else None
    latest_tide = df["tide_mean_m"].dropna().iloc[0] if not df["tide_mean_m"].dropna().empty else None
    latest_range = None
    if not df["tide_max_m"].dropna().empty and not df["tide_min_m"].dropna().empty:
        latest_range = df["tide_max_m"].dropna().iloc[0] - df["tide_min_m"].dropna().iloc[0]

    # KPI row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Sea Surface Temperature",
            f"{latest_sst:.2f} °C" if latest_sst is not None else "N/A",
            help="Daily mean SST from Copernicus"
        )

    with col2:
        st.metric(
            "Chlorophyll-a",
            f"{latest_chl:.3f} mg/m³" if latest_chl is not None else "N/A",
            help="Daily mean chlorophyll concentration"
        )

    with col3:
        st.metric(
            "Tide Mean Level",
            f"{latest_tide:.3f} m" if latest_tide is not None else "N/A"
        )

    with col4:
        st.metric(
            "Tide Range",
            f"{latest_range:.3f} m" if latest_range is not None else "N/A"
        )

    # Simple alerts
    st.subheader("Alerts & Status")
    alerts = []

    if latest_sst is not None and latest_sst > 29:
        alerts.append(("error", f"High SST detected: {latest_sst:.2f} °C"))
    elif latest_sst is not None and latest_sst > 28:
        alerts.append(("warning", f"Elevated SST: {latest_sst:.2f} °C"))

    if latest_chl is not None and latest_chl > 1.0:
        alerts.append(("warning", f"Elevated chlorophyll: {latest_chl:.3f} mg/m³ (possible bloom)"))

    if not alerts:
        st.success("All monitored indicators within normal range for the Western Indian Ocean.")
    else:
        for level, msg in alerts:
            if level == "error":
                st.error(msg)
            else:
                st.warning(msg)

    # Data table
    st.subheader("Recent Daily Conditions")
    st.dataframe(
        df.style.format({
            "sst_celsius": "{:.3f}",
            "chlorophyll_mg_m3": "{:.4f}",
            "tide_mean_m": "{:.3f}",
            "tide_min_m": "{:.3f}",
            "tide_max_m": "{:.3f}"
        }),
        use_container_width=True
    )