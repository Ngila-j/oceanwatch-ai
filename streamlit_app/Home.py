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
st.subheader("Western Indian Ocean · Kenya EEZ monitoring")
st.caption("Ocean · port · fishing effort · anomalies · WIO intelligence index")

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=60)
def load_kpis():
    eng = create_engine(DB_URI, pool_pre_ping=True)
    out = {"error": None}

    def one(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            out["error"] = str(e)
            return pd.DataFrame()

    out["sst"] = one(
        """
        SELECT date_key, sst_celsius FROM fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key DESC LIMIT 1
        """
    )
    out["idx"] = one(
        """
        SELECT overall_score, confidence_score, index_date
        FROM fact_wio_intelligence_index
        ORDER BY index_date DESC LIMIT 1
        """
    )
    out["alerts"] = one(
        "SELECT COUNT(*) AS n FROM fact_alerts WHERE status = 'OPEN'"
    )
    out["anoms"] = one(
        """
        SELECT COUNT(*) AS n FROM fact_oceanwatch_anomalies
        WHERE status IN ('ELEVATED', 'HIGH', 'CRITICAL')
        """
    )
    return out


k = load_kpis()
if k.get("error"):
    st.warning(f"Database issue: {k['error']}")
    st.caption("Start Postgres: docker compose up -d")
else:
    c1, c2, c3, c4 = st.columns(4)
    sst, idx = k["sst"], k["idx"]
    c1.metric(
        "Latest SST (°C)",
        f"{float(sst.iloc[0]['sst_celsius']):.2f}" if not sst.empty else "—",
        help=str(sst.iloc[0]["date_key"]) if not sst.empty else None,
    )
    c2.metric(
        "WIO-OII",
        f"{float(idx.iloc[0]['overall_score']):.1f}" if not idx.empty else "—",
        help=f"As of {idx.iloc[0]['index_date']}" if not idx.empty else "Run compute_wio_index",
    )
    c3.metric(
        "Open alerts",
        int(k["alerts"].iloc[0]["n"]) if not k["alerts"].empty else 0,
    )
    c4.metric(
        "Elevated anomalies",
        int(k["anoms"].iloc[0]["n"]) if not k["anoms"].empty else 0,
    )

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

st.info(
    "Decision-support prototype for Kenya / Western Indian Ocean. "
    "Not an official authority product. Live AIS may be sparse; SAMPLE supports demos."
)
st.caption("OceanWatch AI · transparent methods · Kenya-first")