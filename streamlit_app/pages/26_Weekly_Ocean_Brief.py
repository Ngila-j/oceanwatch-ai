import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import date

st.set_page_config(page_title="Weekly Ocean Brief", page_icon="📰", layout="wide")
st.title("📰 Weekly Ocean Brief")
st.caption(f"Kenya EEZ · generated {date.today().isoformat()}")

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=60)
def load_brief():
    eng = create_engine(DB_URI, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception:
            return pd.DataFrame()

    return {
        "idx": q(
            """
            SELECT overall_score, confidence_score, index_date, drivers,
                   methodology_version, ocean_health_score, maritime_activity_score,
                   fishing_pressure_score, port_risk_score, environmental_risk_score
            FROM fact_wio_intelligence_index
            ORDER BY index_date DESC LIMIT 1
            """
        ),
        "sst": q(
            """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3
            FROM fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL
            ORDER BY date_key DESC LIMIT 7
            """
        ),
        "anoms": q(
            """
            SELECT metric_name, status, anomaly_pct, explanation, as_of_date
            FROM fact_oceanwatch_anomalies
            ORDER BY as_of_date DESC LIMIT 15
            """
        ),
        "alerts": q(
            """
            SELECT severity, category, title, description, why_it_matters, created_at
            FROM fact_alerts
            WHERE status = 'OPEN'
            ORDER BY created_at DESC LIMIT 15
            """
        ),
    }


data = load_brief()
idx, sst, anoms, alerts = data["idx"], data["sst"], data["anoms"], data["alerts"]

st.markdown("### 1. Headline indicators")
c1, c2, c3, c4 = st.columns(4)
if not idx.empty:
    r = idx.iloc[0]
    c1.metric(
        "WIO-OII",
        f"{float(r['overall_score']):.1f}" if pd.notna(r.get("overall_score")) else "—",
    )
    c2.metric(
        "Confidence",
        f"{float(r['confidence_score']):.0f}" if pd.notna(r.get("confidence_score")) else "—",
    )
    c3.metric("Index date", str(r.get("index_date") or "—"))
    c4.metric("Method", str(r.get("methodology_version") or "—"))
    if r.get("drivers"):
        st.code(str(r["drivers"]), language=None)
else:
    st.info("No WIO-OII yet — run compute_wio_index.py")

if not sst.empty:
    st.markdown("### 2. Recent ocean conditions (up to 7 days)")
    st.dataframe(sst, use_container_width=True)
    if len(sst) and pd.notna(sst.iloc[0].get("sst_celsius")):
        st.caption(f"Latest SST: **{float(sst.iloc[0]['sst_celsius']):.2f} °C**")

st.markdown("### 3. Anomalies")
elevated = (
    anoms[anoms["status"].isin(["ELEVATED", "HIGH", "CRITICAL"])]
    if not anoms.empty and "status" in anoms.columns
    else anoms
)
st.dataframe(
    elevated if elevated is not None and not elevated.empty else pd.DataFrame({"note": ["None elevated"]}),
    use_container_width=True,
)

st.markdown("### 4. Open alerts")
st.dataframe(
    alerts if not alerts.empty else pd.DataFrame({"note": ["None open"]}),
    use_container_width=True,
)

st.markdown("### 5. Share / download")
lines = [
    f"OceanWatch Weekly Ocean Brief — {date.today().isoformat()}",
    "Region: Kenya EEZ / Western Indian Ocean monitoring box",
    "",
]
if not idx.empty:
    r = idx.iloc[0]
    lines.append(
        f"WIO-OII: {r.get('overall_score')} (confidence {r.get('confidence_score')}, "
        f"as of {r.get('index_date')}, method {r.get('methodology_version')})"
    )
    lines.append(f"Drivers: {r.get('drivers')}")
    lines.append("")
lines.append("Open alerts:")
if alerts.empty:
    lines.append("  (none)")
else:
    for _, a in alerts.head(10).iterrows():
        lines.append(f"  - [{a.get('severity')}] {a.get('title')} ({a.get('category')})")
lines.append("")
lines.append("Elevated anomalies:")
if elevated is None or elevated.empty:
    lines.append("  (none)")
else:
    for _, a in elevated.head(10).iterrows():
        lines.append(f"  - {a.get('metric_name')} {a.get('status')} ({a.get('as_of_date')})")
lines.append("")
lines.append(
    "Disclaimer: Decision-support prototype only. Not official maritime, fisheries, "
    "or environmental determinations. GFW data: Global Fishing Watch terms/attribution apply."
)
brief_text = "\n".join(lines)

st.download_button(
    label="Download brief (.txt)",
    data=brief_text,
    file_name=f"oceanwatch_weekly_brief_{date.today().isoformat()}.txt",
    mime="text/plain",
)

st.info(
    "For maps and day detail use **Historical Playback**, **Operational Alerts**, "
    "and **WIO Intelligence Index**."
)
st.caption("OceanWatch AI · Kenya-first · transparent methods")