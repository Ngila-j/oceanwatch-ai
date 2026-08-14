import streamlit as st

st.set_page_config(
    page_title="Oceanwatch AI",
    page_icon="🌊",
    layout="wide"
)

st.title("🌊 Oceanwatch AI")
st.markdown("### Western Indian Ocean / Mombasa Monitoring Platform")

st.markdown("""
This platform monitors ocean conditions in the **Kenya EEZ / Western Indian Ocean** region.

**Available pages:**
- **Executive Summary** – Key metrics and latest conditions
- **GIS Live Map** – Interactive spatial view of the monitoring area
- **Ocean Conditions** – SST, Chlorophyll and Tide trends
""")

st.info("Data sources: NOAA Tides & Currents + Copernicus Marine Service")