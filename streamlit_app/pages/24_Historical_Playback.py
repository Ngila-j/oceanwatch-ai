"""Historical Playback — review stored ocean / alert state by date."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Historical Playback", page_icon=":material/history:", layout="wide")

try:
    from ow_theme import apply_theme, init_a11y_defaults
    init_a11y_defaults(); apply_theme()
except Exception:
    pass
st.title("Historical Playback")
st.caption("Browse stored daily snapshots. Prototype decision-support only.")

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=120)
def available_dates():
    eng = create_engine(DB, pool_pre_ping=True)
    try:
        return pd.read_sql(
            text(
                """
                SELECT DISTINCT date_key::date AS d
                FROM fact_ocean_conditions
                WHERE date_key IS NOT NULL
                ORDER BY 1 DESC
                LIMIT 120
                """
            ),
            eng,
        )
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_day(day: str):
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql, params=None):
        try:
            return pd.read_sql(text(sql), eng, params=params or {})
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "ocean": q(
            """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3, tide_mean_m, tide_min_m, tide_max_m
            FROM fact_ocean_conditions
            WHERE date_key::date = :d
            """,
            {"d": day},
        ),
        "alerts": q(
            """
            SELECT category, severity, title, risk_score, status, created_at
            FROM fact_alerts
            WHERE created_at::date = :d
            ORDER BY created_at DESC
            LIMIT 50
            """,
            {"d": day},
        ),
        "port": q(
            """
            SELECT *
            FROM fact_port_metrics
            WHERE metric_date = :d
            """,
            {"d": day},
        ),
    }


dates = available_dates()
if dates.empty:
    st.warning("No dates in fact_ocean_conditions yet.")
    st.stop()

day = st.selectbox("Playback date", options=[str(x) for x in dates["d"].tolist()])
data = load_day(day)

c1, c2, c3 = st.columns(3)
oc = data["ocean"]
if not oc.empty and "error" not in oc.columns:
    row = oc.iloc[0]
    c1.metric("SST (C)", f"{row['sst_celsius']:.2f}" if pd.notna(row.get("sst_celsius")) else "—")
    c2.metric("CHL", f"{row['chlorophyll_mg_m3']:.3f}" if pd.notna(row.get("chlorophyll_mg_m3")) else "—")
    c3.metric("Tide mean (m)", f"{row['tide_mean_m']:.2f}" if pd.notna(row.get("tide_mean_m")) else "—")
else:
    st.info("No ocean row for this date.")

st.subheader("Port metrics that day")
pt = data["port"]
if pt is not None and not pt.empty and "error" not in pt.columns:
    st.dataframe(pt, width="stretch")
else:
    st.caption("No port metrics for this date.")

st.subheader("Alerts created that day")
al = data["alerts"]
if al is not None and not al.empty and "error" not in al.columns:
    st.dataframe(al, width="stretch")
else:
    st.caption("No alerts logged on this date.")