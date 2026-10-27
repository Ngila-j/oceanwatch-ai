"""Phase 13 — Ocean Intelligence fusion dashboard (Kenya EEZ)."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        import os

        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")


st.set_page_config(page_title="Ocean Intelligence", page_icon="🌊", layout="wide")
st.title("Ocean Intelligence")
st.caption(
    "Climate anomalies · bloom/habitat fusion · environmental early warning · Kenya EEZ. "
    "Decision-support only — not an official ecological or health advisory."
)


def _sa_uri(uri: str) -> str:
    if not uri:
        return uri
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


DB = get_db_uri()


@st.cache_data(ttl=45)
def load():
    if not DB:
        empty = pd.DataFrame({"error": ["No database URI configured."]})
        return {"fusion": empty, "anom": empty, "warn": empty, "sst": empty}

    eng = create_engine(_sa_uri(DB), pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:  # noqa: BLE001
            return pd.DataFrame({"error": [str(e)]})

    return {
        "fusion": q(
            "SELECT * FROM fact_ocean_risk_fusion ORDER BY as_of_date DESC LIMIT 5"
        ),
        "anom": q(
            "SELECT * FROM fact_ocean_climate_anomalies ORDER BY as_of_date DESC, metric LIMIT 20"
        ),
        "warn": q(
            """
            SELECT * FROM fact_environmental_warnings
            ORDER BY as_of_date DESC NULLS LAST
            LIMIT 20
            """
        ),
        "sst": q(
            """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3
            FROM fact_ocean_conditions
            WHERE sst_celsius IS NOT NULL
            ORDER BY date_key
            """
        ),
    }


d = load()

fusion = d.get("fusion")
if fusion is None or fusion.empty or "error" in getattr(fusion, "columns", []):
    err = None
    if fusion is not None and not fusion.empty and "error" in fusion.columns:
        err = fusion.iloc[0].get("error")
    st.warning(
        "No fusion rows. Run `python ingestion/init_phase13_ocean.py` and "
        "`python ingestion/run_phase13_ocean.py`"
        + (f"\n\n({err})" if err else "")
    )
    st.stop()

f = fusion.iloc[0]

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric(
    "Composite ocean risk",
    f.get("composite_ocean_risk"),
    str(f.get("risk_level")),
)
c2.metric("Climate risk", f.get("climate_risk_score"))
c3.metric("Bloom risk", f.get("bloom_risk_score"))
c4.metric("Habitat stress", f.get("habitat_stress_score"))
c5.metric("Confidence", f.get("confidence_score"))

if f.get("early_warning_flag"):
    st.error(f.get("early_warning_message") or "Early warning active")
else:
    st.success("No early-warning threshold crossed for current fusion snapshot.")

st.caption(f"As-of {f.get('as_of_date')} · {f.get('drivers')} · model {f.get('model_version')}")

left, right = st.columns(2)

with left:
    st.subheader("Climate anomalies")
    anom = d.get("anom")
    if anom is not None and not anom.empty and "error" not in anom.columns:
        show = [
            c
            for c in (
                "as_of_date",
                "metric",
                "current_value",
                "mean_7d",
                "mean_30d",
                "anomaly_pct",
                "severity",
                "confidence_score",
            )
            if c in anom.columns
        ]
        st.dataframe(anom[show], use_container_width=True, hide_index=True)
    else:
        st.info("No climate anomaly rows.")

with right:
    st.subheader("Environmental warnings")
    warn = d.get("warn")
    if warn is not None and not warn.empty and "error" not in warn.columns:
        show = [
            c
            for c in (
                "as_of_date",
                "warning_type",
                "severity",
                "title",
                "message",
                "metric_value",
                "status",
            )
            if c in warn.columns
        ]
        st.dataframe(warn[show], use_container_width=True, hide_index=True)
    else:
        st.info("No open environmental warnings.")

st.subheader("Fusion snapshot")
st.dataframe(fusion, use_container_width=True, hide_index=True)

sst = d.get("sst")
if sst is not None and not sst.empty and "error" not in sst.columns and "date_key" in sst.columns:
    st.subheader("SST history (ocean conditions)")
    plot_df = sst.dropna(subset=["sst_celsius"]).tail(90).copy()
    if not plot_df.empty:
        fig = px.line(plot_df, x="date_key", y="sst_celsius", title="SST (°C)")
        st.plotly_chart(fig, use_container_width=True)
    if "chlorophyll_mg_m3" in sst.columns:
        chl = sst.dropna(subset=["chlorophyll_mg_m3"]).tail(90)
        if not chl.empty:
            fig2 = px.line(chl, x="date_key", y="chlorophyll_mg_m3", title="Chlorophyll (mg/m³)")
            st.plotly_chart(fig2, use_container_width=True)

st.caption(
    "Fused climate · bloom · habitat signals for Kenya EEZ. "
    "Not an official ecological or health advisory."
)
