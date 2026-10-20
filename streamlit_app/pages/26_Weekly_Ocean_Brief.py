"""Weekly Ocean Brief — auto narrative from latest warehouse facts."""

from datetime import datetime

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:
    def get_db_uri():
        import os
        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/oceanwatch_db"

st.set_page_config(page_title="Weekly Ocean Brief", page_icon=":material/newspaper:", layout="wide")

try:
    from ow_theme import apply_theme, init_a11y_defaults
    init_a11y_defaults(); apply_theme()
except Exception:
    pass
st.title("Weekly Ocean Brief")
st.caption("Auto-generated summary for Kenya EEZ / Mombasa. Not an official bulletin.")

DB = get_db_uri()
@st.cache_data(ttl=120)
def load_brief_inputs():
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
            WHERE sst_celsius IS NOT NULL
            ORDER BY date_key DESC
            LIMIT 14
            """
        ),
        "port": q(
            """
            SELECT metric_date, congestion_level, active_vessels, congestion_index, avg_waiting_hours
            FROM fact_port_metrics
            ORDER BY metric_date DESC
            LIMIT 1
            """
        ),
        "wio": q(
            """
            SELECT index_date, overall_score, confidence_score, drivers
            FROM fact_wio_intelligence_index
            ORDER BY index_date DESC
            LIMIT 1
            """
        ),
        "gfw": q(
            """
            SELECT COALESCE(SUM(hours),0) AS hours, COUNT(*) AS cells,
                   MIN(effort_date) AS start_d, MAX(effort_date) AS end_d
            FROM fact_gfw_fishing_effort
            """
        ),
        "alerts": q(
            """
            SELECT severity, title, category, risk_score
            FROM fact_alerts
            WHERE status = 'OPEN'
            ORDER BY risk_score DESC NULLS LAST
            LIMIT 8
            """
        ),
    }


d = load_brief_inputs()
today = datetime.utcnow().strftime("%Y-%m-%d")

sst_line = "SST history limited."
if not d["ocean"].empty:
    latest = d["ocean"].iloc[0]
    oldest = d["ocean"].iloc[-1]
    sst_line = (
        f"Latest SST {latest['sst_celsius']:.2f} C (as of {latest['date_key']}). "
        f"Compared with earlier sample {oldest['sst_celsius']:.2f} C ({oldest['date_key']})."
    )

port_line = "Port metrics not available."
if not d["port"].empty:
    p = d["port"].iloc[0]
    port_line = (
        f"Mombasa congestion {p.get('congestion_level')} "
        f"(index {p.get('congestion_index')}), active vessels {p.get('active_vessels')}, "
        f"avg wait {p.get('avg_waiting_hours')} h (metric date {p.get('metric_date')})."
    )

wio_line = "WIO-OII not computed yet."
if not d["wio"].empty:
    w = d["wio"].iloc[0]
    wio_line = (
        f"WIO-OII overall {w.get('overall_score')} "
        f"(confidence {w.get('confidence_score')}) on {w.get('index_date')}."
    )

gfw_line = "No GFW effort rows stored."
if not d["gfw"].empty:
    g = d["gfw"].iloc[0]
    gfw_line = (
        f"Stored GFW effort ~{float(g.get('hours') or 0):.0f} hours "
        f"across {int(g.get('cells') or 0)} cells "
        f"({g.get('start_d')} to {g.get('end_d')}). "
        "Powered by Global Fishing Watch where applicable."
    )

alert_lines = []
if not d["alerts"].empty:
    for _, r in d["alerts"].iterrows():
        alert_lines.append(
            f"- [{r.get('severity')}] {r.get('title')} ({r.get('category')}, risk={r.get('risk_score')})"
        )
else:
    alert_lines = ["- No open alerts."]

brief = f"""OceanWatch Weekly Ocean Brief
Generated (UTC): {today}
Region: Kenya EEZ / Mombasa focus

1. Ocean conditions
{sst_line}

2. Port operations
{port_line}

3. Regional index
{wio_line}

4. Fishing effort (stored)
{gfw_line}

5. Open alerts
{chr(10).join(alert_lines)}

Disclaimer
Decision-support prototype only. Not an official government or GFW product.
Validate against primary sources before operational use.
"""

st.text_area("Brief", brief, height=420)
st.download_button(
    "Download brief (.txt)",
    data=brief,
    file_name=f"oceanwatch_brief_{today}.txt",
    mime="text/plain",
)

st.subheader("Open alerts table")
if not d["alerts"].empty:
    st.dataframe(d["alerts"], width="stretch")