"""Kenya EEZ Today — operational heart of OceanWatch (Kenya-first)."""

from datetime import datetime

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Kenya EEZ Today", page_icon=":material/public:", layout="wide")
st.title("Kenya EEZ — Today")
st.caption("Operational snapshot for Kenya EEZ / Mombasa. Decision-support only.")

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=45)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception:
            return pd.DataFrame()

    return {
        "ocean": q(
            """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3
            FROM fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL OR chlorophyll_mg_m3 IS NOT NULL
            ORDER BY date_key DESC LIMIT 1
            """
        ),
        "port": q(
            """
            SELECT * FROM fact_port_metrics
            ORDER BY metric_date DESC LIMIT 1
            """
        ),
        "wio": q(
            """
            SELECT * FROM fact_wio_intelligence_index
            ORDER BY index_date DESC LIMIT 1
            """
        ),
        "gfw": q(
            """
            SELECT COALESCE(SUM(hours),0) AS hours, MAX(effort_date) AS last_day
            FROM fact_gfw_fishing_effort
            """
        ),
        "ais_n": q(
            """
            SELECT COUNT(DISTINCT mmsi) AS vessels, MAX(event_time) AS last_ais
            FROM fact_ais_positions
            """
        ),
        "events": q(
            """
            SELECT severity, event_category, title, risk_score, confidence_score,
                   evidence, source, created_at
            FROM oceanwatch_events
            WHERE status = 'OPEN'
            ORDER BY risk_score DESC NULLS LAST, created_at DESC
            LIMIT 12
            """
        ),
        "risks": q(
            """
            SELECT domain, entity_id, risk_score, confidence_score, risk_level,
                   reason, data_freshness_minutes, model_version
            FROM risk_scores
            ORDER BY created_at DESC
            LIMIT 12
            """
        ),
        "forecast": q(
            """
            SELECT forecast_for_date, horizon_day, predicted_sst, model_name
            FROM fact_sst_forecast
            ORDER BY horizon_day
            LIMIT 7
            """
        ),
        "alerts": q(
            """
            SELECT category, severity, title, risk_score, created_at
            FROM fact_alerts
            WHERE status = 'OPEN'
            ORDER BY risk_score DESC NULLS LAST
            LIMIT 8
            """
        ),
    }


def freshness_label(ts) -> str:
    if ts is None or (isinstance(ts, float) and pd.isna(ts)):
        return "UNKNOWN"
    try:
        t = pd.to_datetime(ts).to_pydatetime()
        if getattr(t, "tzinfo", None):
            t = t.replace(tzinfo=None)
        mins = (datetime.utcnow() - t).total_seconds() / 60.0
        if mins < 180:
            return f"FRESH (~{mins:.0f}m)"
        if mins < 24 * 60:
            return f"DELAYED (~{mins/60:.1f}h)"
        return f"STALE (~{mins/1440:.1f}d)"
    except Exception:
        return "UNKNOWN"


d = load()

# KPI row
vessels = open_ev = sst = chl = cong = wio = "—"
if not d["ais_n"].empty:
    vessels = int(d["ais_n"].iloc[0].get("vessels") or 0)
if not d["events"].empty:
    open_ev = len(d["events"])
elif not d["alerts"].empty:
    open_ev = len(d["alerts"])
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

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Vessels (stored AIS)", vessels)
c2.metric("Priority events", open_ev)
c3.metric("SST (C)", sst)
c4.metric("CHL", chl)
c5.metric("Port congestion", cong)
c6.metric("WIO-OII", wio)

st.subheader("Data health")
h1, h2, h3, h4 = st.columns(4)
ocean_ts = d["ocean"].iloc[0]["date_key"] if not d["ocean"].empty else None
port_ts = d["port"].iloc[0]["metric_date"] if not d["port"].empty else None
ais_ts = d["ais_n"].iloc[0]["last_ais"] if not d["ais_n"].empty else None
gfw_ts = d["gfw"].iloc[0]["last_day"] if not d["gfw"].empty else None
h1.write(f"**Ocean (SST/CHL)** · {freshness_label(ocean_ts)}")
h2.write(f"**Port metrics** · {freshness_label(port_ts)}")
h3.write(f"**AIS** · {freshness_label(ais_ts)}")
h4.write(f"**GFW** · {freshness_label(gfw_ts)}")

st.subheader("Priority intelligence")
if not d["events"].empty:
    st.dataframe(d["events"], width="stretch")
elif not d["alerts"].empty:
    st.caption("Events table empty — showing OPEN alerts.")
    st.dataframe(d["alerts"], width="stretch")
else:
    st.caption("No priority events. Run detect_events.py after pipeline.")

st.subheader("Risk scores (unified frame)")
if not d["risks"].empty:
    st.dataframe(d["risks"], width="stretch")
else:
    st.caption("No risk_scores rows yet.")

st.subheader("Forecast — next days (SST)")
if not d["forecast"].empty:
    st.dataframe(d["forecast"], width="stretch")
else:
    st.caption("No SST forecast rows.")

st.info(
    "Human review required for vessel flags. "
    "Scores include confidence and freshness where available. "
    "Not a legal or official government product."
)