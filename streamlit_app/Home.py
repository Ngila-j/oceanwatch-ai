"""
OceanWatch AI — Home hub
Maps the product canvas (8 Level-1 sections) to existing pages.
Does not replace deeper pages; only organizes entry.
"""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="OceanWatch AI",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🌊 OceanWatch AI")
st.caption(
    "Western Indian Ocean · Kenya EEZ monitoring · "
    "Ocean · port · fishing effort · anomalies · WIO intelligence index"
)

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=60)
def load_kpis():
    eng = create_engine(DB, pool_pre_ping=True)

    def one(sql, default=None):
        try:
            df = pd.read_sql(text(sql), eng)
            if df is None or df.empty:
                return default
            return df.iloc[0, 0]
        except Exception:
            return default

    return {
        "sst": one(
            "SELECT sst_celsius FROM fact_ocean_conditions "
            "WHERE sst_celsius IS NOT NULL ORDER BY date_key DESC LIMIT 1"
        ),
        "wio": one(
            "SELECT overall_score FROM fact_wio_intelligence_index "
            "ORDER BY index_date DESC LIMIT 1"
        ),
        "alerts": one(
            "SELECT COUNT(*) FROM fact_alerts WHERE status = 'OPEN'",
            0,
        ),
        "anoms": one(
            """
            SELECT COUNT(*) FROM fact_oceanwatch_anomalies
            WHERE UPPER(COALESCE(status, severity, '')) IN ('ELEVATED', 'HIGH', 'CRITICAL')
            """,
            0,
        ),
    }


k = load_kpis()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Latest SST (°C)", f"{k['sst']:.2f}" if k["sst"] is not None else "—")
c2.metric("WIO-OII", f"{k['wio']:.1f}" if k["wio"] is not None else "—")
c3.metric("Open alerts", int(k["alerts"] or 0))
c4.metric("Elevated anomalies", int(k["anoms"] or 0))

st.markdown("### Daily workflow")
st.markdown(
    """
1. **Home** — KPIs  
2. **Operational Alerts** — what changed  
3. **WIO Intelligence Index** — signature score  
4. **Weekly Ocean Brief** — download and share  
5. **Historical Playback** — any stored day  
"""
)

st.markdown("---")
st.markdown("### Product canvas — main sections")
st.caption(
    "Matches OceanWatch dashboard navigation (Level 1). "
    "Open a section to reach live pages you already built."
)

# 8 Level-1 sections → existing pages (non-breaking links)
SECTIONS = [
    {
        "title": "1 · Overview & Intelligence",
        "color": "#1f6feb",
        "blurb": "Executive view, WIO-OII, Kenya EEZ today, situation brief.",
        "links": [
            ("Executive Summary", "pages/1_Executive_Summary.py"),
            ("WIO Intelligence Index", "pages/18_WIO_Intelligence_Index.py"),
            ("Weekly Ocean Brief", "pages/26_Weekly_Ocean_Brief.py"),
            ("Quality & Provenance", "pages/25_Quality_and_Provenance.py"),
        ],
    },
    {
        "title": "2 · Ocean & Environment",
        "color": "#2da44e",
        "blurb": "SST, chlorophyll, climate indicators, bloom & habitat signals.",
        "links": [
            ("Ocean Conditions", "pages/3_Ocean_Conditions.py"),
            ("Fisheries and Climate", "pages/5_Fisheries_and_Climate.py"),
            ("Bloom Risk", "pages/12_Bloom_Risk.py"),
            ("Habitat Suitability", "pages/13_Habitat_Suitability.py"),
        ],
    },
    {
        "title": "3 · Maritime & Vessels",
        "color": "#8250df",
        "blurb": "AIS positions, tracks, behaviour scores (SAMPLE + live path).",
        "links": [
            ("Vessel Tracking", "pages/4_Vessel_Tracking.py"),
            ("AIS Live", "pages/10_AIS_Live.py"),
        ],
    },
    {
        "title": "4 · Fisheries & Activity",
        "color": "#bf8700",
        "blurb": "Fishing activity, GFW effort, effort-related alerts.",
        "links": [
            ("Fishing Activity", "pages/9_Fishing_Activity.py"),
            ("GFW Fishing Effort", "pages/15_GFW_Fishing_Effort.py"),
        ],
    },
    {
        "title": "5 · Ports & Infrastructure",
        "color": "#0969da",
        "blurb": "Mombasa port metrics, congestion, operational risk.",
        "links": [
            ("Port Intelligence", "pages/8_Port_Intelligence.py"),
            ("Port Risk", "pages/11_Port_Risk.py"),
        ],
    },
    {
        "title": "6 · Risks & Alerts",
        "color": "#cf222e",
        "blurb": "Open alerts, enrichment, subscriptions (outbox delivery).",
        "links": [
            ("Operational Alerts", "pages/7_Operational_Alerts.py"),
            ("Alert Subscriptions", "pages/17_Alert_Subscriptions.py"),
        ],
    },
    {
        "title": "7 · Data, Research & Analytics",
        "color": "#9a6700",
        "blurb": "Research access, datasets, transparent methods.",
        "links": [
            ("Research Data", "pages/16_Research_Data.py"),
            ("Quality & Provenance", "pages/25_Quality_and_Provenance.py"),
        ],
    },
    {
        "title": "8 · Platform & System",
        "color": "#656d76",
        "blurb": "Onboarding, system posture, API health (prototype).",
        "links": [
            ("Onboarding and Access", "pages/19_Onboarding_and_Access.py"),
            ("System Health", "pages/20_System_Health.py"),
        ],
    },
]

rows = [SECTIONS[i : i + 2] for i in range(0, len(SECTIONS), 2)]
for row in rows:
    cols = st.columns(2)
    for col, sec in zip(cols, row):
        with col:
            st.markdown(
                f"""
                <div style="border-left:6px solid {sec['color']};
                            background:#f6f8fa;padding:1rem 1.1rem;
                            border-radius:8px;margin-bottom:0.75rem;min-height:140px;">
                  <div style="font-weight:700;font-size:1.05rem;margin-bottom:0.35rem;">
                    {sec['title']}
                  </div>
                  <div style="color:#57606a;font-size:0.9rem;margin-bottom:0.5rem;">
                    {sec['blurb']}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            for label, path in sec["links"]:
                try:
                    st.page_link(path, label=f"→ {label}")
                except Exception:
                    st.caption(f"→ {label} *(page file not found yet)*")

st.markdown("---")
st.info(
    "Decision-support prototype for Kenya / Western Indian Ocean. "
    "Not an official authority product. Live AIS may be sparse; SAMPLE supports demos. "
    "GFW-related views require Global Fishing Watch attribution where applicable."
)
st.caption("OceanWatch AI · transparent methods · Kenya-first · canvas IA v1")