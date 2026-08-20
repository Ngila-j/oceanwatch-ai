import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(page_title="System Health", page_icon="🩺", layout="wide")
st.title("🩺 System Health & Data Quality")
st.caption("Phase 10 observability — freshness and quality for operators.")

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_resource
def get_engine():
    return create_engine(DB_URI, pool_pre_ping=True)


@st.cache_data(ttl=60)
def load_quality():
    engine = get_engine()
    try:
        return pd.read_sql(
            """
            SELECT DISTINCT ON (dataset_name)
                dataset_name, overall_score, completeness, validity, timeliness,
                consistency, records_total, records_flagged, last_observation,
                status, notes, scored_at
            FROM fact_data_quality
            ORDER BY dataset_name, scored_at DESC
            """,
            engine,
        )
    except Exception as e:
        st.warning(f"Quality table missing — run compute_data_quality.py ({e})")
        return pd.DataFrame()


@st.cache_data(ttl=60)
def load_freshness():
    engine = get_engine()
    # Use real column names for this project
    queries = {
        "ocean_conditions": "SELECT MAX(date_key) AS last_ts FROM fact_ocean_conditions",
        "ais_positions": "SELECT MAX(event_time) AS last_ts FROM fact_ais_positions",
        "gfw_effort": "SELECT MAX(effort_date) AS last_ts FROM fact_gfw_fishing_effort",
        "wio_index": "SELECT MAX(index_date) AS last_ts FROM fact_wio_intelligence_index",
        "port_metrics": "SELECT MAX(metric_date) AS last_ts FROM fact_port_metrics",
        "alerts": "SELECT MAX(created_at) AS last_ts FROM fact_alerts",
        "data_quality": "SELECT MAX(scored_at) AS last_ts FROM fact_data_quality",
    }
    rows = []
    for name, sql in queries.items():
        try:
            df = pd.read_sql(text(sql), engine)
            rows.append({"dataset": name, "last_update": df.iloc[0]["last_ts"]})
        except Exception:
            rows.append({"dataset": name, "last_update": None})
    return pd.DataFrame(rows)


q = load_quality()
f = load_freshness()

st.subheader("Data freshness")
st.dataframe(f, use_container_width=True)

st.subheader("Quality scores")
if q.empty:
    st.info("No quality rows yet. Run: python /opt/airflow/ingestion/compute_data_quality.py")
else:
    n = min(4, len(q))
    cols = st.columns(n) if n else []
    for i, (_, row) in enumerate(q.iterrows()):
        with cols[i % n]:
            st.metric(
                str(row["dataset_name"]),
                f"{float(row['overall_score']):.0f}",
                delta=str(row["status"]),
            )
    st.dataframe(q, use_container_width=True)

st.markdown(
    """
### Status guide
- **HEALTHY** — overall ≥ 80  
- **DEGRADED** — investigate validity/timeliness  
- Quality is a **transparency** metric, not a legal guarantee of source correctness.
"""
)