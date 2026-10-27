"""OceanWatch AI — 7-day SST forecast for Kenya EEZ."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        import os

        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")


st.set_page_config(page_title="AI SST Forecast", page_icon="📈", layout="wide")
st.title("OceanWatch AI SST Forecast")
st.caption("7-day Sea Surface Temperature forecast for the Kenya EEZ monitoring area")


def _sa_uri(uri: str) -> str:
    if not uri:
        return uri
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


@st.cache_data(ttl=120)
def load_data():
    uri = get_db_uri()
    if not uri:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), "No database URI configured."
    engine = create_engine(_sa_uri(uri), pool_pre_ping=True)
    try:
        hist = pd.read_sql(
            text(
                """
                SELECT date_key::date AS date, sst_celsius AS mean_sst
                FROM fact_ocean_conditions
                WHERE sst_celsius IS NOT NULL
                ORDER BY date_key
                """
            ),
            engine,
        )
    except Exception as e:  # noqa: BLE001
        hist = pd.DataFrame()
        hist_err = str(e)
    else:
        hist_err = None

    try:
        fc = pd.read_sql(
            text(
                """
                SELECT forecast_for_date, horizon_day, predicted_sst, lower_bound, upper_bound,
                       model_name, model_version, mae, rmse, forecast_date
                FROM fact_sst_forecast
                ORDER BY horizon_day
                """
            ),
            engine,
        )
        metrics = pd.read_sql(
            text(
                """
                SELECT model_name, target, mae, rmse, train_rows, test_rows, is_best, trained_at
                FROM ml_model_metrics
                ORDER BY mae
                """
            ),
            engine,
        )
        return hist, fc, metrics, None
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "fact_sst_forecast" in msg or "UndefinedTable" in msg or "does not exist" in msg:
            return (
                hist,
                pd.DataFrame(),
                pd.DataFrame(),
                "No SST forecast data yet. Run `python ingestion/ml_sst_forecast.py` "
                "(creates `fact_sst_forecast` + `ml_model_metrics` and seeds a 7-day outlook).",
            )
        return hist, pd.DataFrame(), pd.DataFrame(), f"Could not load forecast: {msg}" + (
            f" | hist: {hist_err}" if hist_err else ""
        )


hist, fc, metrics, err = load_data()
if err:
    st.warning(err)
    st.stop()

if fc is None or fc.empty:
    st.info(
        "No forecast rows. Run `python ingestion/ml_sst_forecast.py` to seed "
        "`fact_sst_forecast`."
    )
    st.stop()

model_name = fc["model_name"].iloc[0] if "model_name" in fc.columns else "—"
mae_v = fc["mae"].iloc[0] if "mae" in fc.columns else None
rmse_v = fc["rmse"].iloc[0] if "rmse" in fc.columns else None
as_of = fc["forecast_date"].iloc[0] if "forecast_date" in fc.columns else None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Model", str(model_name))
c2.metric("MAE (°C)", f"{float(mae_v):.3f}" if mae_v is not None and pd.notna(mae_v) else "—")
c3.metric("RMSE (°C)", f"{float(rmse_v):.3f}" if rmse_v is not None and pd.notna(rmse_v) else "—")
c4.metric("Forecast as-of", str(as_of) if as_of is not None else "—")

# Chart: history + forecast bands
fig = go.Figure()
if hist is not None and not hist.empty and "date" in hist.columns and "mean_sst" in hist.columns:
    h = hist.dropna(subset=["mean_sst"]).tail(60).copy()
    h["date"] = pd.to_datetime(h["date"], errors="coerce")
    fig.add_trace(
        go.Scatter(
            x=h["date"],
            y=h["mean_sst"],
            mode="lines",
            name="Observed SST",
            line=dict(color="#1f77b4"),
        )
    )

fc_plot = fc.copy()
fc_plot["forecast_for_date"] = pd.to_datetime(fc_plot["forecast_for_date"], errors="coerce")
fig.add_trace(
    go.Scatter(
        x=fc_plot["forecast_for_date"],
        y=fc_plot["predicted_sst"],
        mode="lines+markers",
        name="Predicted SST",
        line=dict(color="#ff7f0e"),
    )
)
if "upper_bound" in fc_plot.columns and "lower_bound" in fc_plot.columns:
    fig.add_trace(
        go.Scatter(
            x=list(fc_plot["forecast_for_date"]) + list(fc_plot["forecast_for_date"][::-1]),
            y=list(fc_plot["upper_bound"]) + list(fc_plot["lower_bound"][::-1]),
            fill="toself",
            fillcolor="rgba(255,127,14,0.15)",
            line=dict(color="rgba(255,255,255,0)"),
            name="Uncertainty band",
            hoverinfo="skip",
        )
    )

fig.update_layout(
    title="7-day SST forecast",
    xaxis_title="Date",
    yaxis_title="SST (°C)",
    hovermode="x unified",
    height=420,
)
st.plotly_chart(fig, use_container_width=True)

left, right = st.columns(2)
with left:
    st.subheader("Forecast table")
    show = [
        c
        for c in (
            "horizon_day",
            "forecast_for_date",
            "predicted_sst",
            "lower_bound",
            "upper_bound",
            "model_name",
        )
        if c in fc.columns
    ]
    st.dataframe(fc[show], use_container_width=True, hide_index=True)

with right:
    st.subheader("Model comparison")
    if metrics is not None and not metrics.empty:
        st.dataframe(metrics, use_container_width=True, hide_index=True)
        if "model_name" in metrics.columns and "mae" in metrics.columns:
            bar = px.bar(metrics, x="model_name", y="mae", title="MAE by model (°C)")
            st.plotly_chart(bar, use_container_width=True)
    else:
        st.info("No ml_model_metrics rows.")

st.caption(
    "Decision-support SST outlook for Kenya EEZ. "
    "Naive persistence baseline; Ridge/GBR use lag/rolling/calendar features when history allows."
)
