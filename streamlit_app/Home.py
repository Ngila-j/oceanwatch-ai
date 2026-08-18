import streamlit as st

st.set_page_config(
    page_title="OceanWatch AI",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🌊 OceanWatch AI")
st.subheader("Western Indian Ocean · Kenya EEZ · Mombasa operational intelligence")

st.markdown(
    """
OceanWatch fuses **Copernicus**, **NOAA**, **AIS**, and **Global Fishing Watch** into
decision-ready views for ports, fisheries, maritime security, environment, and research.
"""
)

st.markdown("### Choose your workspace")

roles = {
    "🚢 Port operations (KPA / operators)": {
        "focus": "Port efficiency, congestion, waiting time, operational risk",
        "pages": [
            ("Port Intelligence", "pages/8_Port_Intelligence.py"),
            ("Port Risk", "pages/12_Port_Risk.py"),
            ("Operational Alerts", "pages/7_Operational_Alerts.py"),
            ("AIS Live", "pages/11_AIS_Live.py"),
        ],
        "api": "/v1/port/risk",
    },
    "🐟 Fisheries / BMU": {
        "focus": "Fishing conditions, GFW effort, habitat suitability, bloom risk",
        "pages": [
            ("Fishing Activity", "pages/9_Fishing_Activity.py"),
            ("GFW Fishing Effort", "pages/15_GFW_Fishing_Effort.py"),
            ("Habitat Suitability", "pages/14_Habitat_Suitability.py"),
            ("Fisheries & Climate", "pages/5_Fisheries_and_Climate.py"),
        ],
        "api": "/v1/gfw/effort/summary",
    },
    "🛡️ Coast Guard / Navy (MDA)": {
        "focus": "Maritime domain awareness, vessel anomalies, EEZ activity",
        "pages": [
            ("Vessel Tracking", "pages/4_Vessel_Tracking.py"),
            ("AIS Live", "pages/11_AIS_Live.py"),
            ("Operational Alerts", "pages/7_Operational_Alerts.py"),
            ("GIS Live Map", "pages/2_GIS_Live_Map.py"),
        ],
        "api": "/v1/alerts",
    },
    "🌿 NEMA / Environment": {
        "focus": "SST, chlorophyll, bloom probability, climate indicators",
        "pages": [
            ("Ocean Conditions", "pages/3_Ocean_Conditions.py"),
            ("Bloom Risk", "pages/13_Bloom_Risk.py"),
            ("AI Forecasts", "pages/6_AI_Forecasts.py"),
            ("Executive Summary", "pages/1_Executive_Summary.py"),
        ],
        "api": "/v1/ocean/conditions",
    },
    "🎓 Research / University": {
        "focus": "Clean tables, forecasts, ML metrics, partner API",
        "pages": [
            ("Executive Summary", "pages/1_Executive_Summary.py"),
            ("AI Forecasts", "pages/6_AI_Forecasts.py"),
            ("GFW Fishing Effort", "pages/15_GFW_Fishing_Effort.py"),
            ("Ocean Conditions", "pages/3_Ocean_Conditions.py"),
        ],
        "api": "/docs",
    },
}

choice = st.selectbox("User segment", list(roles.keys()))
info = roles[choice]

st.info(f"**Focus:** {info['focus']}")

cols = st.columns(2)
with cols[0]:
    st.markdown("**Recommended views**")
    for label, path in info["pages"]:
        try:
            st.page_link(path, label=f"→ {label}")
        except Exception:
            st.markdown(f"- {label}")

with cols[1]:
    st.markdown("**Partner API**")
    st.code(f"GET http://localhost:8000{info['api']}", language="text")
    st.caption("OpenAPI docs: http://localhost:8000/docs")

st.markdown("---")
st.markdown("### Data layers")

c1, c2 = st.columns(2)
with c1:
    st.success(
        """
**Public / shareable**
- Daily SST & chlorophyll summaries
- Tide statistics
- SST forecasts (model metrics)
- GFW effort aggregates (with attribution)
"""
    )
with c2:
    st.warning(
        """
**Restricted / operational**
- Vessel-level anomaly scores
- Live AIS positions (when available)
- Port congestion internals
- Named alert evidence trails
"""
    )

st.markdown("---")
st.markdown("### Alert subscriptions (Phase 8 foundation)")
with st.form("subscribe_stub"):
    seg = st.selectbox("Segment", list(roles.keys()), key="sub_seg")
    channel = st.selectbox("Channel", ["Email", "WhatsApp (later)", "Webhook URL"])
    dest = st.text_input("Destination (email / phone / URL)")
    events = st.multiselect(
        "Events",
        [
            "Port congestion HIGH",
            "Bloom risk ELEVATED",
            "Vessel anomaly HIGH",
            "SST anomaly",
            "GFW effort spike",
        ],
        default=["Port congestion HIGH", "Bloom risk ELEVATED"],
    )
    submitted = st.form_submit_button("Save preference (local stub)")
    if submitted:
        st.session_state["subscription_stub"] = {
            "segment": seg,
            "channel": channel,
            "destination": dest,
            "events": events,
        }
        st.success(
            "Saved in this browser session only. "
            "Production email/WhatsApp delivery comes later — no messages sent now."
        )

if "subscription_stub" in st.session_state:
    st.json(st.session_state["subscription_stub"])

st.markdown("---")
st.caption(
    "OceanWatch AI · Kenya-first · Non-commercial research/education layers where applicable. "
    "Fishing effort powered by Global Fishing Watch · https://globalfishingwatch.org"
)