"""
OceanWatch AI — main shell
Grouped sidebar (canvas Level 1). Material icons (no emoji).
Each page registered at most once. Sidebar titles strip numeric filename prefixes.
"""

import re
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


def clean_title(stem: str) -> str:
    """0_Kenya_EEZ_Today -> Kenya EEZ Today"""
    s = re.sub(r"^\d+[_\-\s]*", "", stem)
    s = s.replace("_", " ").strip()
    return s.title() if s else stem


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

# --- Core pages ---
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
quality = page(
    "pages/25_Quality_and_Provenance.py",
    "Quality & Provenance",
    ":material/verified:",
    url_path="quality_provenance",
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
    or page("pages/11_Bloom_Risk.py", "Bloom Risk", ":material/eco:")
    or page("pages/13_Bloom_Risk.py", "Bloom Risk", ":material/eco:")
)
habitat = (
    page("pages/13_Habitat_Suitability.py", "Habitat Suitability", ":material/forest:")
    or page("pages/12_Habitat_Suitability.py", "Habitat Suitability", ":material/forest:")
    or page("pages/14_Habitat_Suitability.py", "Habitat Suitability", ":material/forest:")
)

vessel = page(
    "pages/4_Vessel_Tracking.py",
    "Vessel Tracking",
    ":material/directions_boat:",
)
ais = (
    page("pages/10_AIS_Live.py", "AIS Live", ":material/cell_tower:")
    or page("pages/11_AIS_Live.py", "AIS Live", ":material/cell_tower:")
    or page("pages/AIS_Live.py", "AIS Live", ":material/cell_tower:")
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

port = page(
    "pages/8_Port_Intelligence.py",
    "Port Intelligence",
    ":material/anchor:",
)
port_risk = (
    page("pages/11_Port_Risk.py", "Port Risk", ":material/analytics:")
    or page("pages/12_Port_Risk.py", "Port Risk", ":material/analytics:")
    or page("pages/Port_Risk.py", "Port Risk", ":material/analytics:")
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

research = page(
    "pages/16_Research_Data.py",
    "Research Data",
    ":material/menu_book:",
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

methodology = (
    page("pages/21_Methodology_and_Sources.py", "Methodology and Sources", ":material/menu_book:")
    or page("pages/Methodology_and_Sources.py", "Methodology and Sources", ":material/menu_book:")
)
api_access = page("pages/22_API_Access.py", "API Access", ":material/api:") or page(
    "pages/API_Access.py", "API Access", ":material/api:"
)
anomaly_engine = page(
    "pages/23_Anomaly_Engine.py", "Anomaly Engine", ":material/psychology:"
) or page("pages/Anomaly_Engine.py", "Anomaly Engine", ":material/psychology:")
playback = page(
    "pages/24_Historical_Playback.py", "Historical Playback", ":material/history:"
) or page("pages/Historical_Playback.py", "Historical Playback", ":material/history:")
intel_map = page(
    "pages/2_Intelligence_Map.py", "Intelligence Map", ":material/map:"
) or page("pages/Intelligence_Map.py", "Intelligence Map", ":material/map:")
ai_forecasts = page(
    "pages/6_AI_Forecasts.py", "AI Forecasts", ":material/trending_up:"
) or page("pages/AI_Forecasts.py", "AI Forecasts", ":material/trending_up:")

used_names = {
    "Home.py",
    "0_Kenya_EEZ_Today.py",
    "Kenya_EEZ_Today.py",
    "1_Executive_Summary.py",
    "2_Intelligence_Map.py",
    "Intelligence_Map.py",
    "3_Ocean_Conditions.py",
    "4_Vessel_Tracking.py",
    "5_Fisheries_and_Climate.py",
    "6_AI_Forecasts.py",
    "AI_Forecasts.py",
    "7_Operational_Alerts.py",
    "8_Port_Intelligence.py",
    "9_Fishing_Activity.py",
    "10_AIS_Live.py",
    "11_AIS_Live.py",
    "11_Port_Risk.py",
    "12_Port_Risk.py",
    "11_Bloom_Risk.py",
    "12_Bloom_Risk.py",
    "13_Bloom_Risk.py",
    "12_Habitat_Suitability.py",
    "13_Habitat_Suitability.py",
    "14_Habitat_Suitability.py",
    "15_GFW_Fishing_Effort.py",
    "16_Research_Data.py",
    "17_Alert_Subscriptions.py",
    "18_WIO_Intelligence_Index.py",
    "19_Onboarding_and_Access.py",
    "20_System_Health.py",
    "21_Methodology_and_Sources.py",
    "Methodology_and_Sources.py",
    "22_API_Access.py",
    "API_Access.py",
    "23_Anomaly_Engine.py",
    "Anomaly_Engine.py",
    "24_Historical_Playback.py",
    "Historical_Playback.py",
    "25_Quality_and_Provenance.py",
    "26_Weekly_Ocean_Brief.py",
}

extra = []
if PAGES.is_dir():
    for f in sorted(PAGES.glob("*.py")):
        if f.name.startswith("_") or f.name in used_names:
            continue
        slug = re.sub(r"^\d+[_\-\s]*", "", f.stem).lower().replace(" ", "_")
        if not slug:
            slug = f.stem.lower()
        extra.append(
            st.Page(
                f"pages/{f.name}",
                title=clean_title(f.stem),
                icon=":material/description:",
                url_path=slug,
            )
        )

nav_dict = {
    "Overview & Intelligence": keep(home, kenya, exec_sum, wio, brief, intel_map),
    "Ocean & Environment": keep(ocean, fish_clim, bloom, habitat, ai_forecasts),
    "Maritime & Vessels": keep(vessel, ais),
    "Fisheries & Activity": keep(fishing, gfw),
    "Ports & Infrastructure": keep(port, port_risk),
    "Risks & Alerts": keep(alerts, subs, anomaly_engine),
    "Data, Research & Analytics": keep(research, quality, methodology, api_access, playback),
    "Platform & System": keep(onboard, health, *extra),
}
nav_dict = {k: v for k, v in nav_dict.items() if v}

if not nav_dict:
    st.error("No pages found. Check streamlit_app/pages.")
    st.stop()

nav = st.navigation(nav_dict, position="sidebar")
nav.run()