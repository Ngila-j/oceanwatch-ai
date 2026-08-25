import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

from components.branding import attribution_footer, bandwidth_toggle

st.set_page_config(page_title="Anomaly Engine", page_icon="📉", layout="wide")
bandwidth_toggle()

st.title("📉 OceanWatch Anomaly Engine")
st.caption("Is this unusual vs recent baselines? Decision-support only.")

DB_URI = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=60)
def load():
    eng = create_engine(DB_URI, pool_pre_ping=True)
    try:
        return pd.read_sql(
            text(
                """
                SELECT metric_name, as_of_date, current_value, baseline_value,
                       anomaly_value, anomaly_pct, status, window_days, explanation, created_at
                FROM fact_oceanwatch_anomalies
                ORDER BY created_at DESC, metric_name
                """
            ),
            eng,
        )
    except Exception as e:
        st.warning(f"Run compute_anomalies.py first ({e})")
        return pd.DataFrame()


df = load()
if df.empty:
    st.info(
        "No anomalies yet. Run:\n"
        "`docker exec -it oceanwatch_airflow_web python /opt/airflow/ingestion/compute_anomalies.py`"
    )
else:
    for status in ["CRITICAL", "HIGH", "ELEVATED", "NORMAL", "UNKNOWN"]:
        sub = df[df["status"] == status]
        if sub.empty:
            continue
        st.subheader(status)
        st.dataframe(sub, use_container_width=True)

attribution_footer()