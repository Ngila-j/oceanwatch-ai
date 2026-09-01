"""
OceanWatch AI — Home (cockpit)
KPIs + trends + open alerts. Navigation lives in the sidebar.
"""

from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="OceanWatch Home",
    page_icon=":material/home:",
    layout="wide",
)

try:
    from ow_theme import apply

    apply()
except Exception:
    pass

st.title("OceanWatch AI")
st.caption(
    "Kenya EEZ / Mombasa focus · Western Indian Ocean intelligence · "
    "Decision-support prototype (not an official authority product)"
)

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=60)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception:
            return pd.DataFrame()

    return {
        "ocean_latest": q(
            """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3
            FROM fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL OR chlorophyll_mg_m3 IS NOT NULL
            ORDER BY date_key DESC
            LIMIT 1
            """
        ),
        "ocean_series": q(
            """
            SELECT date_key::timestamp AS date_key, sst_celsius, chlorophyll_mg_m3
            FROM fact_ocean_conditions
            WHERE date_key IS NOT NULL
            ORDER BY date_key DESC
            LIMIT 45
            """
        ),
        "port": q(
            """
            SELECT metric_date, congestion_level, active_vessels, congestion_index
            FROM fact_port_metrics
            ORDER BY metric_date DESC
            LIMIT 1
            """
        ),
        "wio": q(
            """
            SELECT index_date, overall_score, confidence_score
            FROM fact_wio_intelligence_index
            ORDER BY index_date DESC
            LIMIT 1
            """
        ),
        "gfw": q(
            """
            SELECT COALESCE(SUM(hours), 0) AS hours,
                   MAX(effort_date) AS last_day
            FROM fact_gfw_fishing_effort
            """
        ),
        "alerts": q(
            """
            SELECT category, severity, title, risk_score, created_at
            FROM fact_alerts
            WHERE status = 'OPEN'
            ORDER BY risk_score DESC NULLS LAST, created_at DESC
            LIMIT 8
            """
        ),
        "alert_counts": q(
            """
            SELECT status, COUNT(*) AS n
            FROM fact_alerts
            GROUP BY status
            """
        ),
    }


d = load()

# ----- Freshness strip -----
ocean_asof = port_asof = wio_asof = gfw_asof = "—"
if not d["ocean_latest"].empty:
    ocean_asof = str(d["ocean_latest"].iloc[0].get("date_key", "—"))
if not d["port"].empty:
    port_asof = str(d["port"].iloc[0].get("metric_date", "—"))
if not d["wio"].empty:
    wio_asof = str(d["wio"].iloc[0].get("index_date", "—"))
if not d["gfw"].empty and d["gfw"].iloc[0].get("last_day") is not None:
    gfw_asof = str(d["gfw"].iloc[0].get("last_day"))

st.markdown(
    f"**Data as of** · Ocean: `{ocean_asof}` · Port: `{port_asof}` · "
    f"WIO-OII: `{wio_asof}` · GFW: `{gfw_asof}` · "
    f"Refreshed: `{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC`"
)

# ----- KPI row -----
sst = chl = wio_s = cong = vessels = gfw_h = open_n = "—"

if not d["ocean_latest"].empty:
    r = d["ocean_latest"].iloc[0]
    if pd.notna(r.get("sst_celsius")):
        sst = f"{float(r['sst_celsius']):.2f}"
    if pd.notna(r.get("chlorophyll_mg_m3")):
        chl = f"{float(r['chlorophyll_mg_m3']):.3f}"

if not d["wio"].empty and pd.notna(d["wio"].iloc[0].get("overall_score")):
    wio_s = f"{float(d['wio'].iloc[0]['overall_score']):.1f}"

if not d["port"].empty:
    p = d["port"].iloc[0]
    cong = str(p.get("congestion_level") or "—")
    vessels = p.get("active_vessels", "—")

if not d["gfw"].empty and pd.notna(d["gfw"].iloc[0].get("hours")):
    gfw_h = f"{float(d['gfw'].iloc[0]['hours']):.0f}"

if not d["alert_counts"].empty:
    open_rows = d["alert_counts"][d["alert_counts"]["status"] == "OPEN"]
    if not open_rows.empty:
        open_n = int(open_rows.iloc[0]["n"])

k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
k1.metric("SST (C)", sst)
k2.metric("CHL", chl)
k3.metric("WIO-OII", wio_s)
k4.metric("Port congestion", cong)
k5.metric("Active vessels", vessels)
k6.metric("GFW hours", gfw_h)
k7.metric("Open alerts", open_n)

st.divider()

# ----- Charts -----
series = d["ocean_series"].copy()
if not series.empty:
    series = series.sort_values("date_key")
    left, right = st.columns(2)

    with left:
        st.subheader("Sea surface temperature")
        sst_df = series.dropna(subset=["sst_celsius"])
        if not sst_df.empty:
            fig = px.line(
                sst_df,
                x="date_key",
                y="sst_celsius",
                labels={"date_key": "Date", "sst_celsius": "SST (C)"},
            )
            fig.update_layout(
                margin=dict(l=10, r=10, t=20, b=10),
                height=320,
                plot_bgcolor="white",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            fig.update_traces(line_color="#1677C8")
            st.plotly_chart(fig, width="stretch")
        else:
            st.caption("No SST series available.")

    with right:
        st.subheader("Chlorophyll-a")
        chl_df = series.dropna(subset=["chlorophyll_mg_m3"])
        if not chl_df.empty:
            fig2 = px.line(
                chl_df,
                x="date_key",
                y="chlorophyll_mg_m3",
                labels={"date_key": "Date", "chlorophyll_mg_m3": "CHL (mg/m3)"},
            )
            fig2.update_layout(
                margin=dict(l=10, r=10, t=20, b=10),
                height=320,
                plot_bgcolor="white",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            fig2.update_traces(line_color="#16A6A0")
            st.plotly_chart(fig2, width="stretch")
        else:
            st.caption("No chlorophyll series available.")
else:
    st.info("No ocean time series in the warehouse yet. Run the daily pipeline / Copernicus ingest.")

st.divider()

# ----- Alerts -----
st.subheader("Open alerts")
alerts = d["alerts"]
if alerts is not None and not alerts.empty:
    st.dataframe(alerts, width="stretch")
else:
    st.caption("No open alerts.")

st.caption(
    "Use the sidebar for full modules (map, port, GFW, ML, research). "
    "GFW-related figures require Global Fishing Watch attribution where applicable."
)