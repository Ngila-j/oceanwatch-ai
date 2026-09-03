"""Phase 14 — Port Intelligence advanced (Mombasa)."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Port Intelligence Advanced",
    page_icon=":material/anchor:",
    layout="wide",
)
st.title("Port Intelligence — Mombasa")
st.caption(
    "Performance · congestion & arrival forecasts · berth pressure · operational risk"
)

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=45)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "perf": q(
            "SELECT * FROM fact_port_performance ORDER BY metric_date DESC LIMIT 30"
        ),
        "cong": q(
            "SELECT * FROM fact_port_congestion_forecast ORDER BY horizon_day"
        ),
        "arr": q(
            "SELECT * FROM fact_port_arrival_forecast ORDER BY horizon_day"
        ),
        "berth": q(
            "SELECT * FROM fact_berth_pressure ORDER BY as_of_date DESC LIMIT 1"
        ),
        "ops": q(
            "SELECT * FROM fact_port_ops_risk ORDER BY as_of_date DESC LIMIT 1"
        ),
    }


d = load()

if d["ops"] is None or d["ops"].empty or "error" in d["ops"].columns:
    st.warning("No Phase 14 data. Run init_phase14_port.py and run_phase14_port.py")
    st.stop()

ops = d["ops"].iloc[0]
berth = d["berth"].iloc[0] if d["berth"] is not None and not d["berth"].empty else None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ops risk", ops.get("composite_ops_risk"), str(ops.get("risk_level")))
c2.metric("Congestion score", ops.get("congestion_score"))
c3.metric("Traffic score", ops.get("traffic_score"))
c4.metric(
    "Berth pressure",
    berth.get("pressure_score") if berth is not None else "—",
    str(berth.get("pressure_level")) if berth is not None else None,
)

st.caption(f"Drivers: {ops.get('drivers')} · Model: {ops.get('model_version')}")

if berth is not None:
    st.subheader("Berth pressure")
    a, b, c = st.columns(3)
    a.metric("Active vessels", berth.get("active_vessels"))
    b.metric("Capacity proxy", berth.get("capacity_proxy"))
    c.metric("Utilization %", berth.get("berth_utilization_pct"))

st.subheader("Port performance (recent)")
if d["perf"] is not None and not d["perf"].empty and "error" not in d["perf"].columns:
    st.dataframe(d["perf"], width="stretch")
    if len(d["perf"]) > 1:
        fig = px.line(
            d["perf"].sort_values("metric_date"),
            x="metric_date",
            y="performance_score",
            markers=True,
            title="Performance score",
        )
        st.plotly_chart(fig, width="stretch")
else:
    st.caption("No performance rows")

st.subheader("Congestion forecast (7 day)")
if d["cong"] is not None and not d["cong"].empty and "error" not in d["cong"].columns:
    st.dataframe(d["cong"], width="stretch")
    fig = px.line(
        d["cong"],
        x="forecast_date",
        y="predicted_congestion_index",
        markers=True,
        title="Predicted congestion index",
    )
    st.plotly_chart(fig, width="stretch")
else:
    st.caption("No congestion forecast")

st.subheader("Arrival / departure forecast")
if d["arr"] is not None and not d["arr"].empty and "error" not in d["arr"].columns:
    st.dataframe(d["arr"], width="stretch")
    melt = d["arr"].melt(
        id_vars=["forecast_date", "horizon_day"],
        value_vars=["predicted_arrivals", "predicted_departures"],
        var_name="flow",
        value_name="vessels",
    )
    fig = px.line(melt, x="forecast_date", y="vessels", color="flow", markers=True)
    st.plotly_chart(fig, width="stretch")
else:
    st.caption("No arrival forecast")

st.info(
    "Capacity proxy and forecasts are decision-support models for demo/ops planning — "
    "not official port authority figures."
)