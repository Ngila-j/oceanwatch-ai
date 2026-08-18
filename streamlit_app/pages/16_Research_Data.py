import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
from io import StringIO

st.set_page_config(page_title="Research Data", page_icon="🎓", layout="wide")
st.title("🎓 Research Data Explorer")
st.caption(
    "Structured access to OceanWatch datasets for research. "
    "GFW layers: powered by Global Fishing Watch · non-commercial use."
)

DATASETS = {
    "Ocean Conditions": {
        "table": "fact_ocean_conditions",
        "date_col": "date_key",
        "access": "PUBLIC",
    },
    "SST Forecast": {
        "table": "fact_sst_forecast",
        "date_col": "forecast_for_date",
        "access": "PUBLIC",
    },
    "GFW Fishing Effort": {
        "table": "fact_gfw_fishing_effort",
        "date_col": "effort_date",
        "access": "PUBLIC",
    },
    "ML Model Metrics": {
        "table": "ml_model_metrics",
        "date_col": None,
        "access": "PUBLIC",
    },
    "Bloom Risk": {
        "table": "fact_bloom_risk",
        "date_col": "risk_date",
        "access": "RESTRICTED",
    },
    "Port Risk": {
        "table": "fact_port_risk",
        "date_col": "risk_date",
        "access": "RESTRICTED",
    },
    "Alerts": {
        "table": "fact_alerts",
        "date_col": None,
        "access": "RESTRICTED",
    },
}

engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")

ds_name = st.selectbox("Dataset", list(DATASETS.keys()))
meta = DATASETS[ds_name]
st.info(f"Table: `{meta['table']}` · Access tier: **{meta['access']}**")

limit = st.slider("Preview rows", 10, 500, 100)

sql = f"SELECT * FROM {meta['table']} LIMIT {int(limit)}"
try:
    df = pd.read_sql(sql, engine)
except Exception as e:
    st.error(f"Could not load dataset: {e}")
    st.stop()

st.subheader("Preview")
st.dataframe(df, use_container_width=True)
st.metric("Rows in preview", len(df))

csv = df.to_csv(index=False)
st.download_button(
    label="Download CSV (preview)",
    data=csv,
    file_name=f"oceanwatch_{meta['table']}_preview.csv",
    mime="text/csv",
)

st.markdown("---")
st.markdown(
    """
**API access**

```text
GET http://localhost:8000/v1/ocean/conditions
GET http://localhost:8000/v1/forecasts/sst
GET http://localhost:8000/v1/gfw/effort/summary
GET http://localhost:8000/docs