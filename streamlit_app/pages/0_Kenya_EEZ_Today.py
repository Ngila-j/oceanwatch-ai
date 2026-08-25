from pathlib import Path

import pandas as pd
import streamlit as st

from components.branding import (
    attribution_footer,
    bandwidth_toggle,
    is_low_bandwidth,
    methodology_blurb,
)
from components.data_access import list_briefs, qdf

st.set_page_config(page_title="Kenya EEZ Today", page_icon="🇰🇪", layout="wide")
bandwidth_toggle()

st.title("🇰🇪 Kenya EEZ / Mombasa — Today")
st.caption(
    "One-screen operational snapshot. Free open intelligence for Kenya’s Western Indian Ocean coast."
)
methodology_blurb()

port = qdf("SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 1")
wio = qdf(
    "SELECT * FROM fact_wio_intelligence_index ORDER BY index_date DESC LIMIT 1"
)
ocean_latest = qdf(
    """
    SELECT date_key, sst_celsius, chlorophyll_mg_m3
    FROM fact_ocean_conditions
    WHERE sst_celsius IS NOT NULL OR chlorophyll_mg_m3 IS NOT NULL
    ORDER BY date_key DESC
    LIMIT 1
    """
)
ocean_hist = qdf(
    """
    SELECT date_key, sst_celsius, chlorophyll_mg_m3
    FROM fact_ocean_conditions
    WHERE sst_celsius IS NOT NULL
    ORDER BY date_key DESC
    LIMIT 30
    """
)
alerts = qdf(
    """
    SELECT category, severity, title, risk_score, created_at
    FROM fact_alerts
    ORDER BY created_at DESC
    LIMIT 5
    """
)
quality = qdf(
    """
    SELECT DISTINCT ON (dataset_name)
        dataset_name, overall_score, status, scored_at
    FROM fact_data_quality
    ORDER BY dataset_name, scored_at DESC
    """
)
gfw = qdf(
    """
    SELECT COUNT(*) AS cells, COALESCE(SUM(hours), 0) AS hours,
           MAX(effort_date) AS last_day
    FROM fact_gfw_fishing_effort
    """
)

# Last-update stamps
st.markdown("##### Data as of")
u1, u2, u3, u4 = st.columns(4)
u1.write(f"Ocean: **{ocean_latest.iloc[0]['date_key'] if not ocean_latest.empty else '—'}**")
u2.write(f"Port: **{port.iloc[0]['metric_date'] if not port.empty else '—'}**")
u3.write(f"WIO-OII: **{wio.iloc[0]['index_date'] if not wio.empty else '—'}**")
u4.write(f"GFW last day: **{gfw.iloc[0]['last_day'] if not gfw.empty else '—'}**")

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    st.metric(
        "Port congestion",
        str(port.iloc[0]["congestion_level"]) if not port.empty else "—",
    )
with c2:
    st.metric(
        "Active vessels",
        str(port.iloc[0]["active_vessels"]) if not port.empty else "—",
    )
with c3:
    if not ocean_latest.empty and pd.notna(ocean_latest.iloc[0].get("sst_celsius")):
        st.metric("SST (°C)", f"{float(ocean_latest.iloc[0]['sst_celsius']):.2f}")
    else:
        st.metric("SST (°C)", "—")
with c4:
    if not ocean_latest.empty and pd.notna(ocean_latest.iloc[0].get("chlorophyll_mg_m3")):
        st.metric("CHL", f"{float(ocean_latest.iloc[0]['chlorophyll_mg_m3']):.3f}")
    else:
        st.metric("CHL", "—")
with c5:
    st.metric(
        "WIO-OII",
        f"{float(wio.iloc[0]['overall_score']):.1f}" if not wio.empty else "—",
    )
with c6:
    st.metric(
        "GFW hours (stored)",
        f"{float(gfw.iloc[0]['hours']):.0f}" if not gfw.empty else "—",
    )

st.markdown("#### Recent alerts")
if alerts.empty:
    st.write("No alerts in database.")
else:
    st.dataframe(alerts, use_container_width=True)

left, right = st.columns(2)
with left:
    st.markdown("#### Port snapshot")
    if port.empty:
        st.write("No port metrics yet.")
    else:
        p = port.iloc[0]
        st.write(
            f"- Date: **{p.get('metric_date')}**\n"
            f"- Arrivals: **{p.get('arrivals')}** · Departures: **{p.get('departures')}**\n"
            f"- Avg wait (h): **{p.get('avg_waiting_hours')}**\n"
            f"- vs 30d baseline: **{p.get('vs_30d_baseline_pct')}%**"
        )
        st.caption("May include modelled/sample activity — check System Health.")

with right:
    st.markdown("#### WIO-OII drivers")
    if wio.empty:
        st.write("No index row yet.")
    else:
        w = wio.iloc[0]
        st.write(
            f"- Region: **{w.get('region_id')}** · Confidence: **{w.get('confidence_score')}**\n"
            f"- Method: **{w.get('methodology_version')}**"
        )
        st.code(str(w.get("drivers") or ""), language=None)

# Charts vs low-bandwidth
st.markdown("#### Ocean trend (recent)")
if ocean_hist.empty:
    st.write("No SST history.")
elif is_low_bandwidth():
    st.dataframe(
        ocean_hist.sort_values("date_key"),
        use_container_width=True,
    )
else:
    hist = ocean_hist.sort_values("date_key")
    st.line_chart(hist.set_index("date_key")[["sst_celsius"]])
    if hist["chlorophyll_mg_m3"].notna().any():
        st.line_chart(hist.set_index("date_key")[["chlorophyll_mg_m3"]])

st.markdown("#### Data quality")
if quality.empty:
    st.write("Run compute_data_quality.py to populate scores.")
else:
    st.dataframe(quality, use_container_width=True)

st.markdown("#### Weekly Ocean Brief")
briefs = list_briefs()
if not briefs:
    st.warning(
        "No PDF in `reports/` yet. Run Airflow task `generate_weekly_brief` "
        "or: `python ingestion/generate_weekly_brief.py`"
    )
else:
    latest = briefs[0]
    st.write(f"Latest: **{latest.name}**")
    st.download_button(
        label="Download latest Weekly Ocean Brief (PDF)",
        data=latest.read_bytes(),
        file_name=latest.name,
        mime="application/pdf",
    )
    if len(briefs) > 1 and not is_low_bandwidth():
        with st.expander("Older briefs"):
            for b in briefs[1:6]:
                st.download_button(
                    label=b.name,
                    data=b.read_bytes(),
                    file_name=b.name,
                    mime="application/pdf",
                    key=f"brief_{b.name}",
                )

st.caption("GFW hours are stored aggregates — attribute Global Fishing Watch; check licence for your use.")
attribution_footer()