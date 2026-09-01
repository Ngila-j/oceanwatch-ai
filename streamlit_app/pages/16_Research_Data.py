import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="Research Data", page_icon="ðŸ“š", layout="wide")
st.title("ðŸ“š Research Data Explorer")
st.caption(
    "Read-only access to selected OceanWatch tables for research and portfolio demos. "
    "Respect data licenses (especially Global Fishing Watch)."
)

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"

DATASETS = {
    "fact_ocean_conditions": {
        "sql": """
            SELECT date_key, location_key, sst_celsius, chlorophyll_mg_m3,
                   tide_mean_m, tide_min_m, tide_max_m, loaded_at
            FROM fact_ocean_conditions
            ORDER BY date_key DESC
            LIMIT :limit
        """,
        "access": "PUBLIC / RESEARCH",
        "notes": "Daily ocean conditions (SST, chlorophyll, tides).",
    },
    "fact_sst_forecast": {
        "sql": """
            SELECT forecast_for_date, horizon_day, predicted_sst,
                   lower_bound, upper_bound, model_name, mae
            FROM fact_sst_forecast
            ORDER BY horizon_day
            LIMIT :limit
        """,
        "access": "RESEARCH",
        "notes": "Short-horizon SST forecast outputs.",
    },
    "fact_wio_intelligence_index": {
        "sql": """
            SELECT index_date, region_id, overall_score, confidence_score,
                   ocean_health_score, maritime_activity_score,
                   fishing_pressure_score, port_risk_score,
                   environmental_risk_score, methodology_version, drivers
            FROM fact_wio_intelligence_index
            ORDER BY index_date DESC
            LIMIT :limit
        """,
        "access": "RESEARCH",
        "notes": "WIO-OII prototype index (documented methodology).",
    },
    "fact_gfw_fishing_effort": {
        "sql": """
            SELECT *
            FROM fact_gfw_fishing_effort
            ORDER BY effort_date DESC
            LIMIT :limit
        """,
        "access": "RESEARCH (GFW terms)",
        "notes": "Powered by Global Fishing Watch â€” non-commercial use + attribution.",
    },
    "fact_bloom_risk": {
        "sql": """
            SELECT *
            FROM fact_bloom_risk
            ORDER BY risk_date DESC
            LIMIT :limit
        """,
        "access": "RESEARCH",
        "notes": "Bloom risk probability scores.",
    },
    "dim_regions": {
        "sql": """
            SELECT *
            FROM dim_regions
            ORDER BY is_primary DESC, region_id
            LIMIT :limit
        """,
        "access": "PUBLIC",
        "notes": "Regional coverage model (Kenya ACTIVE; others PLANNED).",
    },
}


@st.cache_resource
def get_engine():
    return create_engine(DB_URI, pool_pre_ping=True)


@st.cache_data(ttl=120)
def load_dataset(name: str, limit: int) -> pd.DataFrame:
    cfg = DATASETS[name]
    engine = get_engine()
    return pd.read_sql(text(cfg["sql"]), engine, params={"limit": limit})


dataset = st.selectbox("Dataset", list(DATASETS.keys()))
limit = st.slider("Row limit", min_value=10, max_value=2000, value=200, step=10)

cfg = DATASETS[dataset]
st.info(f"**Access:** {cfg['access']}  \n**Notes:** {cfg['notes']}")

try:
    df = load_dataset(dataset, limit)
    st.success(f"Loaded {len(df)} rows from `{dataset}`")
    st.dataframe(df, width="stretch")

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download CSV",
        data=csv,
        file_name=f"{dataset}.csv",
        mime="text/csv",
    )
except Exception as e:
    st.error(f"Could not load dataset: {e}")
    st.caption("Ensure Postgres is running on localhost:5433 and the table exists.")

st.markdown("---")
st.markdown(
    """
### Research guidelines
- Use data for analysis and demonstration consistent with source licenses.
- Always attribute Global Fishing Watch where fishing-effort data is shown.
- Do not treat vessel anomaly scores as legal findings.
- For production partner access, use the API at `http://localhost:8000/docs`.
"""
)