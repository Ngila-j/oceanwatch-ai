import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Quality & Provenance", page_icon="🔎", layout="wide")
st.title("🔎 Quality & Provenance")
st.caption("What data we use, how fresh it is, and what we do not claim.")

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=120)
def load_health():
    eng = create_engine(DB_URI, pool_pre_ping=True)
    tables = [
        ("raw_tides", "SELECT COUNT(*) AS n, MAX(t) AS latest FROM raw_tides"),
        (
            "fact_ocean_conditions",
            "SELECT COUNT(*) AS n, MAX(date_key) AS latest FROM fact_ocean_conditions",
        ),
        (
            "fact_ais_positions",
            "SELECT COUNT(*) AS n, MAX(event_time) AS latest FROM fact_ais_positions",
        ),
        (
            "fact_gfw_fishing_effort",
            "SELECT COUNT(*) AS n, MAX(effort_date) AS latest FROM fact_gfw_fishing_effort",
        ),
        (
            "fact_wio_intelligence_index",
            "SELECT COUNT(*) AS n, MAX(index_date) AS latest FROM fact_wio_intelligence_index",
        ),
        (
            "fact_oceanwatch_anomalies",
            "SELECT COUNT(*) AS n, MAX(as_of_date) AS latest FROM fact_oceanwatch_anomalies",
        ),
        (
            "fact_alerts",
            "SELECT COUNT(*) AS n, MAX(created_at) AS latest FROM fact_alerts",
        ),
    ]
    rows = []
    for name, sql in tables:
        try:
            df = pd.read_sql(text(sql), eng)
            rows.append(
                {
                    "dataset": name,
                    "rows": int(df.iloc[0]["n"]),
                    "latest": str(df.iloc[0]["latest"]),
                }
            )
        except Exception as e:
            rows.append({"dataset": name, "rows": None, "latest": str(e)[:80]})
    return pd.DataFrame(rows)


st.subheader("Freshness snapshot")
st.dataframe(load_health(), use_container_width=True)

st.subheader("Source registry")
st.markdown(
    """
| Source | Product | Role in OceanWatch |
|--------|---------|---------------------|
| NOAA Tides & Currents | Water levels | Tide series / port context |
| Copernicus Marine | SST, chlorophyll | Ocean conditions & forecasts |
| AISStream | Live AIS | Vessel positions when coverage allows |
| Global Fishing Watch | Fishing effort | Effort cells (CC BY-NC; attribution required) |
| OceanWatch SAMPLE AIS | Synthetic | Demo continuity when live AIS is sparse |
| OceanWatch models | Anomalies, WIO-OII, ML | Derived intelligence — not legal findings |
"""
)

st.subheader("Limits (read this)")
st.warning(
    """
- **Not official** maritime, fisheries, or environmental determinations.  
- **AISSTREAM** coverage over Kenya can be thin; **SAMPLE** is not real traffic.  
- **GFW** is non-commercial where their licence applies; always attribute.  
- **WIO-OII** is a transparent prototype score (v1.0), not a regulatory index.  
- Anomalies mean “unusual vs recent baseline,” not “illegal.”
"""
)

st.subheader("How to trust a number")
st.markdown(
    """
1. Check **Quality table** above for row counts and latest timestamps.  
2. Open **Methodology and Sources** / this page for definitions.  
3. Open **Operational Alerts** for *why it matters* and data source.  
4. Use **Historical Playback** to see what was stored on a given day.
"""
)

st.caption("OceanWatch AI · Kenya-first · transparent methods")