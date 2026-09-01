import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine

st.set_page_config(page_title="AI Forecasts", page_icon="ðŸ¤–", layout="wide")
st.title("ðŸ¤– OceanWatch AI â€” SST Forecast")
st.caption("7-day Sea Surface Temperature forecast for the Kenya EEZ monitoring area")

@st.cache_data(ttl=180)
def load_data():
    engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")
    hist = pd.read_sql("""
        SELECT date_key AS date, sst_celsius AS mean_sst
        FROM fact_ocean_conditions
        WHERE sst_celsius IS NOT NULL
        ORDER BY date_key
    """, engine)
    fc = pd.read_sql("""
        SELECT forecast_for_date, horizon_day, predicted_sst, lower_bound, upper_bound,
               model_name, mae, rmse
        FROM fact_sst_forecast
        ORDER BY horizon_day
    """, engine)
    metrics = pd.read_sql("SELECT * FROM ml_model_metrics ORDER BY mae", engine)
    return hist, fc, metrics

hist, fc, metrics = load_data()

if fc.empty:
    st.warning("No forecast available. Run the ML pipeline first.")
    st.code("docker exec -it oceanwatch_airflow_web python /opt/airflow/ingestion/ml_sst_forecast.py")
else:
    latest_hist = hist["mean_sst"].iloc[-1] if not hist.empty else None
    day7 = fc[fc["horizon_day"] == 7]["predicted_sst"].values
    day7_val = day7[0] if len(day7) else None

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Current SST", f"{latest_hist:.2f} Â°C" if latest_hist is not None else "N/A")
    c2.metric("7-Day Forecast", f"{day7_val:.2f} Â°C" if day7_val is not None else "N/A")
    c3.metric("Model MAE", f"{fc.iloc[0]['mae']:.3f} Â°C")
    c4.metric("Best Model", fc.iloc[0]["model_name"])

    # Chart with uncertainty band
    fig = go.Figure()
    if not hist.empty:
        fig.add_trace(go.Scatter(
            x=hist["date"], y=hist["mean_sst"],
            name="Observed", mode="lines+markers", line=dict(color="#1f77b4")
        ))
    fig.add_trace(go.Scatter(
        x=fc["forecast_for_date"], y=fc["upper_bound"],
        mode="lines", line=dict(width=0), showlegend=False
    ))
    fig.add_trace(go.Scatter(
        x=fc["forecast_for_date"], y=fc["lower_bound"],
        mode="lines", line=dict(width=0), fill="tonexty",
        fillcolor="rgba(255,127,14,0.2)", name="Uncertainty"
    ))
    fig.add_trace(go.Scatter(
        x=fc["forecast_for_date"], y=fc["predicted_sst"],
        name="Forecast", mode="lines+markers", line=dict(color="#ff7f0e")
    ))
    fig.update_layout(title="SST Observed vs 7-day Forecast", yaxis_title="Â°C")
    st.plotly_chart(fig, width="stretch")

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Forecast Table")
        st.dataframe(fc[["forecast_for_date", "horizon_day", "predicted_sst", "lower_bound", "upper_bound"]],
                     width="stretch")
    with col_b:
        st.subheader("Model Comparison")
        if not metrics.empty:
            st.dataframe(metrics[["model_name", "mae", "rmse", "is_best", "train_rows", "test_rows"]],
                         width="stretch")
            best = metrics[metrics["is_best"] == True]
            if not best.empty:
                st.success(f"Selected model: **{best.iloc[0]['model_name']}** (lowest MAE)")
        else:
            st.caption("No metrics table yet.")

    st.info("Validation uses a temporal split (no future leakage). Naive persistence is the baseline; Ridge uses lag/rolling/calendar features.")