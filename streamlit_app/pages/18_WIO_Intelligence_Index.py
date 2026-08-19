import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine

st.set_page_config(page_title="WIO Intelligence Index", page_icon="🧭", layout="wide")
st.title("🧭 WIO Ocean Intelligence Index (WIO-OII)")
st.caption(
    "Prototype regional score for the Western Indian Ocean. "
    "Kenya EEZ is ACTIVE; other regions are PLANNED placeholders. "
    "Not an official government index."
)

engine = create_engine("postgresql://postgres:password@localhost:5433/oceanwatch_db")


@st.cache_data(ttl=120)
def load_index():
    try:
        return pd.read_sql(
            """
            SELECT * FROM fact_wio_intelligence_index
            ORDER BY index_date DESC
            """,
            engine,
        )
    except Exception as e:
        st.error(f"Index table missing — run compute_wio_index.py: {e}")
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_regions():
    try:
        return pd.read_sql("SELECT * FROM dim_regions ORDER BY is_primary DESC, region_id", engine)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=300)
def load_sources():
    try:
        return pd.read_sql("SELECT * FROM dim_data_sources ORDER BY status, source_id", engine)
    except Exception:
        return pd.DataFrame()


idx = load_index()
regions = load_regions()
sources = load_sources()

if idx.empty:
    st.warning("No index rows yet. Run: `python /opt/airflow/ingestion/compute_wio_index.py`")
    st.stop()

row = idx.iloc[0]

c1, c2, c3 = st.columns(3)
c1.metric("Overall WIO-OII", f"{row.get('overall_score', row.get('overall_index', '—'))}")
c2.metric("Confidence", f"{row.get('confidence_score', '—')}")
c3.metric("Methodology", str(row.get("methodology_version", "—")))

st.subheader(f"Region: {row.get('region_id', 'kenya_eez')} · {row.get('index_date')}")

components = {
    "Ocean Health": row.get("ocean_health_score") or row.get("ocean_score"),
    "Maritime Activity": row.get("maritime_activity_score"),
    "Fishing Pressure": row.get("fishing_pressure_score") or row.get("fishing_score"),
    "Port (inverse risk)": row.get("port_risk_score") or row.get("port_score"),
    "Environment (inverse risk)": row.get("environmental_risk_score") or row.get("environmental_score"),
}
comp_df = pd.DataFrame(
    [{"component": k, "score": v} for k, v in components.items() if v is not None]
)
if not comp_df.empty:
    fig = px.bar(comp_df, x="component", y="score", range_y=[0, 100], text="score")
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

st.markdown("**Drivers**")
st.code(str(row.get("drivers") or "—"))

st.markdown("---")
st.subheader("Regional coverage")
if not regions.empty:
    st.dataframe(regions, use_container_width=True)
else:
    st.info("dim_regions not loaded")

# Placeholder comparison for planned regions
st.subheader("WIO overview (Kenya live · others planned)")
overview = [
    {"region": "Kenya EEZ", "status": "ACTIVE", "score": row.get("overall_score") or row.get("overall_index")},
    {"region": "Tanzania coast", "status": "PLANNED", "score": None},
    {"region": "Seychelles", "status": "PLANNED", "score": None},
    {"region": "N. Mozambique Channel", "status": "PLANNED", "score": None},
]
st.dataframe(pd.DataFrame(overview), use_container_width=True)

st.markdown("---")
st.subheader("Data source registry (provenance)")
if not sources.empty:
    st.dataframe(sources, use_container_width=True)

st.markdown(
    """
### Methodology (v0.2)

| Component | Weight | Notes |
|-----------|--------|--------|
| Ocean Health | 25% | SST proximity to regional norm |
| Maritime Activity | 20% | AIS vessel count − anomaly pressure |
| Fishing Pressure | 20% | GFW effort hours (intelligence coverage) |
| Port (inverse risk) | 20% | Congestion + port risk inverted |
| Environmental (inverse risk) | 15% | Bloom probability inverted + habitat |

Weights are **initial engineering defaults**, not scientifically validated.
Partnerships (KMFRI, KMD, port authorities) are data-acquisition tracks, not code.
"""
)
st.caption("Fishing effort powered by Global Fishing Watch where used.")