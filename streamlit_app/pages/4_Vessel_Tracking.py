import streamlit as st

st.set_page_config(page_title="Vessel Tracking", page_icon="🚢", layout="wide")

try:
    from ow_theme import apply_theme, init_a11y_defaults
    init_a11y_defaults(); apply_theme()
except Exception:
    pass
st.title("Vessel Tracking & AIS Analytics")

st.info("""
**Coming soon in the next phase**

This page will show:
- Historical and near real-time AIS vessel tracks
- Port arrivals / departures for Mombasa
- Anomaly detection (loitering, dark vessels, unusual routes)
- Integration with Global Fishing Watch data layers
""")

st.subheader("Planned Features")
st.markdown("""
- Interactive vessel track map (Kepler.gl / Folium)
- Filtering by vessel type, flag, speed
- Time-series of port calls
- Simple risk / anomaly flags
""")