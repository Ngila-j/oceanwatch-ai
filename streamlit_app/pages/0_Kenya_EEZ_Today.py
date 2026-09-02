"""Kenya EEZ Today — Phase 11 complete ops view."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Kenya EEZ Today", page_icon=":material/public:", layout="wide")
st.title("Kenya EEZ — Today")
st.caption("Phase 11 intelligence core · Kenya-first · Decision-support only")

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=30)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception:
            return pd.DataFrame()

    return {
        "fresh": q("SELECT * FROM data_freshness ORDER BY source_key"),
        "spatial": q("SELECT * FROM spatial_intelligence ORDER BY metric_key"),
        "events": q(
            """
            SELECT severity, event_type, title, risk_score, confidence_score,
                   evidence, source, model_version, created_at
            FROM oceanwatch_events WHERE status='OPEN'
            ORDER BY risk_score DESC NULLS LAST LIMIT 20
            """
        ),
        "risks": q(
            """
            SELECT domain, entity_id, risk_score, confidence_score, risk_level,
                   reason, data_freshness_minutes, model_version
            FROM risk_scores ORDER BY risk_score DESC LIMIT 20
            """
        ),
        "prov": q("SELECT * FROM data_provenance ORDER BY metric_key"),
        "forecast": q(
            """
            SELECT forecast_for_date, horizon_day, predicted_sst, model_name
            FROM fact_sst_forecast ORDER BY horizon_day LIMIT 7
            """
        ),
        "ocean": q(
            """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3 FROM fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL ORDER BY date_key DESC LIMIT 1
            """
        ),
        "port": q("SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 1"),
        "wio": q("SELECT * FROM fact_wio_intelligence_index ORDER BY index_date DESC LIMIT 1"),
    }


d = load()

# KPIs
sst = chl = cong = wio = ves = "—"
if not d["ocean"].empty:
    o = d["ocean"].iloc[0]
    if pd.notna(o.get("sst_celsius")):
        sst = f"{float(o['sst_celsius']):.2f}"
    if pd.notna(o.get("chlorophyll_mg_m3")):
        chl = f"{float(o['chlorophyll_mg_m3']):.3f}"
if not d["port"].empty:
    cong = str(d["port"].iloc[0].get("congestion_level") or "—")
if not d["wio"].empty and pd.notna(d["wio"].iloc[0].get("overall_score")):
    wio = f"{float(d['wio'].iloc[0]['overall_score']):.1f}"
if not d["spatial"].empty:
    m = d["spatial"][d["spatial"]["metric_key"] == "ais_vessels_in_kenya_box"]
    if not m.empty:
        ves = int(m.iloc[0]["metric_value"])

a, b, c, e, f = st.columns(5)
a.metric("SST (C)", sst)
b.metric("CHL", chl)
c.metric("Port", cong)
e.metric("WIO-OII", wio)
f.metric("Vessels in box", ves)

st.subheader("Data freshness")
if not d["fresh"].empty:
    st.dataframe(d["fresh"], width="stretch")
else:
    st.warning("Run run_phase11_intelligence.py")

st.subheader("Spatial intelligence")
if not d["spatial"].empty:
    st.dataframe(d["spatial"], width="stretch")

st.subheader("Priority events")
if not d["events"].empty:
    st.dataframe(d["events"], width="stretch")
else:
    st.caption("No OPEN events")

st.subheader("Unified risk scores")
if not d["risks"].empty:
    st.dataframe(d["risks"], width="stretch")

st.subheader("Provenance")
if not d["prov"].empty:
    st.dataframe(d["prov"], width="stretch")

st.subheader("SST forecast (7 day)")
if not d["forecast"].empty:
    st.dataframe(d["forecast"], width="stretch")

st.info("Vessel flags require human review. Not legal findings. GFW attribution where applicable.")