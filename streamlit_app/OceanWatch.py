"""
OceanWatch AI — main shell
Sidebar groups match product canvas.
Theme: light canvas + deep navy chrome (ow_theme).
Material icons only. Each page registered once.
"""

from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="OceanWatch AI",
    page_icon=":material/waves:",
    layout="wide",
    initial_sidebar_state="expanded",
)

try:
    from ow_theme import apply

    apply()
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
PAGES = ROOT / "pages"


def page(
    rel: str,
    title: str,
    icon: str = ":material/description:",
    default: bool = False,
    url_path: str = None,
):
    candidates = [
        ROOT / rel,
        PAGES / Path(rel).name,
        ROOT / "pages" / Path(rel).name,
    ]
    for path in candidates:
        if path.is_file():
            rel_path = path.relative_to(ROOT).as_posix()
            kwargs = {"title": title, "icon": icon, "default": default}
            if url_path:
                kwargs["url_path"] = url_path
            return st.Page(rel_path, **kwargs)
    return None


def keep(*items):
    return [p for p in items if p is not None]


with st.sidebar:
    st.markdown("### OceanWatch AI")
    st.caption("Western Indian Ocean Intelligence")
    st.markdown("---")

home = page("Home.py", "Home", ":material/home:", default=True)

kenya = (
    page("pages/0_Kenya_EEZ_Today.py", "Kenya EEZ Today", ":material/public:")
    or page("pages/Kenya_EEZ_Today.py", "Kenya EEZ Today", ":material/public:")
)
exec_sum = page(
    "pages/1_Executive_Summary.py",
    "Executive Summary",
    ":material/dashboard:",
)
wio = page(
    "pages/18_WIO_Intelligence_Index.py",
    "WIO Intelligence Index",
    ":material/monitoring:",
)
brief = page(
    "pages/26_Weekly_Ocean_Brief.py",
    "Weekly Ocean Brief",
    ":material/newspaper:",
)
intel_map = (
    page("pages/2_Intelligence_Map.py", "Intelligence Map", ":material/map:")
    or page("pages/Intelligence_Map.py", "Intelligence Map", ":material/map:")
)

ocean = page(
    "pages/3_Ocean_Conditions.py",
    "Ocean Conditions",
    ":material/waves:",
)
fish_clim = page(
    "pages/5_Fisheries_and_Climate.py",
    "Fisheries and Climate",
    ":material/water:",
)
bloom = (
    page("pages/12_Bloom_Risk.py", "Bloom Risk", ":material/eco:")
    or page("pages/13_Bloom_Risk.py", "Bloom Risk", ":material/eco:")
    or page("pages/11_Bloom_Risk.py", "Bloom Risk", ":material/eco:")
)
habitat = (
    page("pages/14_Habitat_Suitability.py", "Habitat Suitability", ":material/forest:")
    or page("pages/13_Habitat_Suitability.py", "Habitat Suitability", ":material/forest:")
    or page("pages/12_Habitat_Suitability.py", "Habitat Suitability", ":material/forest:")
)
ocean_intel = page(
    "pages/28_Ocean_Intelligence.py",
    "Ocean Intelligence",
    ":material/tsunami:",
)
ai_forecasts = (
    page("pages/6_AI_Forecasts.py", "AI Forecasts", ":material/trending_up:")
    or page("pages/AI_Forecasts.py", "AI Forecasts", ":material/trending_up:")
)

vessel = page(
    "pages/4_Vessel_Tracking.py",
    "Vessel Tracking",
    ":material/directions_boat:",
)
ais = (
    page("pages/11_AIS_Live.py", "AIS Live", ":material/cell_tower:")
    or page("pages/10_AIS_Live.py", "AIS Live", ":material/cell_tower:")
    or page("pages/AIS_Live.py", "AIS Live", ":material/cell_tower:")
)
vessel_intel = page(
    "pages/27_Vessel_Intelligence.py",
    "Vessel Intelligence",
    ":material/sailing:",
)

fishing = page(
    "pages/9_Fishing_Activity.py",
    "Fishing Activity",
    ":material/phishing:",
)
gfw = page(
    "pages/15_GFW_Fishing_Effort.py",
    "GFW Fishing Effort",
    ":material/map:",
)
fish_intel = page(
    "pages/30_Fisheries_Intelligence.py",
    "Fisheries Intelligence",
    ":material/phishing:",
)

port = page(
    "pages/8_Port_Intelligence.py",
    "Port Intelligence",
    ":material/anchor:",
)
port_risk = (
    page("pages/12_Port_Risk.py", "Port Risk", ":material/analytics:")
    or page("pages/11_Port_Risk.py", "Port Risk", ":material/analytics:")
)
port_adv = page(
    "pages/29_Port_Intelligence_Advanced.py",
    "Port Intelligence Advanced",
    ":material/anchor:",
)

alerts = page(
    "pages/7_Operational_Alerts.py",
    "Operational Alerts",
    ":material/warning:",
)
subs = page(
    "pages/17_Alert_Subscriptions.py",
    "Alert Subscriptions",
    ":material/notifications:",
)
anomaly_engine = (
    page("pages/23_Anomaly_Engine.py", "Anomaly Engine", ":material/psychology:")
    or page("pages/Anomaly_Engine.py", "Anomaly Engine", ":material/psychology:")
)

research = page(
    "pages/16_Research_Data.py",
    "Research Data",
    ":material/menu_book:",
)
quality = page(
    "pages/25_Quality_and_Provenance.py",
    "Quality & Provenance",
    ":material/verified:",
    url_path="quality_provenance",
)
methodology = (
    page(
        "pages/21_Methodology_and_Sources.py",
        "Methodology and Sources",
        ":material/menu_book:",
    )
    or page(
        "pages/Methodology_and_Sources.py",
        "Methodology and Sources",
        ":material/menu_book:",
    )
)
api_access = page("pages/22_API_Access.py", "API Access", ":material/api:") or page(
    "pages/API_Access.py", "API Access", ":material/api:"
)
playback = (
    page("pages/24_Historical_Playback.py", "Historical Playback", ":material/history:")
    or page("pages/Historical_Playback.py", "Historical Playback", ":material/history:")
)

onboard = page(
    "pages/19_Onboarding_and_Access.py",
    "Onboarding and Access",
    ":material/person:",
)
health = page(
    "pages/20_System_Health.py",
    "System Health",
    ":material/settings:",
)
platform_ops = page(
    "pages/31_Platform_Operations.py",
    "Platform Operations",
    ":material/dns:",
)

nav_dict = {
    "Overview & Intelligence": keep(
        home,
        kenya,
        exec_sum,
        wio,
        brief,
        intel_map,
    ),
    "Ocean & Environment": keep(
        ocean,
        fish_clim,
        bloom,
        habitat,
        ocean_intel,
        ai_forecasts,
    ),
    "Maritime & Vessels": keep(
        vessel,
        ais,
        vessel_intel,
    ),
    "Fisheries & Activity": keep(
        fishing,
        gfw,
        fish_intel,
    ),
    "Ports & Infrastructure": keep(
        port,
        port_risk,
        port_adv,
    ),
    "Risks & Alerts": keep(
        alerts,
        subs,
        anomaly_engine,
    ),
    "Data, Research & Analytics": keep(
        research,
        quality,
        methodology,
        api_access,
        playback,
    ),
    "Platform & System": keep(
        onboard,
        health,
        platform_ops,
    ),
}
nav_dict = {k: v for k, v in nav_dict.items() if v}

nav = st.navigation(nav_dict, position="sidebar")
nav.run()