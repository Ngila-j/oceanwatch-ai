"""
Research Data Explorer — browse live warehouse tables used by OceanWatch.

SQL column lists are aligned to ingestion / ML seed schemas (not invented).
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

try:
    from db_config import get_db_uri
except ImportError:
    def get_db_uri():
        import os
        return (
            os.getenv("OCEANWATCH_DB_URI")
            or os.getenv("DATABASE_URL")
            or "postgresql://postgres:password@localhost:5433/oceanwatch_db"
        )

try:
    from components.pagekit import boot, close_page
except Exception:
    boot = None
    close_page = None

if boot is not None:
    boot(
        "Research Data Explorer",
        "Browse research-facing tables (ocean conditions, forecasts, GFW, bloom risk, regions).",
        chips=[("access", "RESEARCH"), ("scope", "Kenya EEZ + WIO")],
        page_title="Research Data · OceanWatch",
        icon="📚",
    )
else:
    try:
        st.set_page_config(
            page_title="Research Data · OceanWatch",
            page_icon="📚",
            layout="wide",
        )
    except Exception:
        pass
    try:
        from ow_theme import apply_theme, init_a11y_defaults

        init_a11y_defaults()
        apply_theme()
    except Exception:
        pass
    st.title("Research Data Explorer")
    st.caption(
        "Browse research-facing tables (ocean conditions, forecasts, GFW, bloom risk, regions)."
    )

DB_URI = get_db_uri()

# Column lists match CREATE TABLE / seed writers in ingestion/.
# fact_ocean_conditions: no location_key / loaded_at — use region_id / created_at.
DATASETS = {
    "fact_ocean_conditions": {
        "sql": """
            SELECT date_key, sst_celsius, chlorophyll_mg_m3,
                   tide_mean_m, tide_min_m, tide_max_m,
                   region_id, created_at
            FROM fact_ocean_conditions
            ORDER BY date_key DESC
            LIMIT :limit
        """,
        "order_col": "date_key",
        "access": "RESEARCH",
        "notes": "Daily ocean conditions (SST, chlorophyll, tides).",
    },
    "fact_sst_forecast": {
        "sql": """
            SELECT forecast_date, forecast_for_date, horizon_day, predicted_sst,
                   lower_bound, upper_bound, model_name, model_version, mae, rmse, created_at
            FROM fact_sst_forecast
            ORDER BY forecast_for_date DESC, horizon_day ASC
            LIMIT :limit
        """,
        "order_col": "forecast_for_date",
        "access": "RESEARCH",
        "notes": "ML SST forecast horizons with uncertainty bounds.",
    },
    "fact_wio_intelligence_index": {
        "sql": """
            SELECT index_date, region_id,
                   ocean_health_score, maritime_activity_score, fishing_pressure_score,
                   port_risk_score, environmental_risk_score, overall_score,
                   confidence_score, drivers, methodology_version, created_at
            FROM fact_wio_intelligence_index
            ORDER BY index_date DESC
            LIMIT :limit
        """,
        "order_col": "index_date",
        "access": "RESEARCH",
        "notes": "Composite WIO intelligence index and component scores.",
    },
    "fact_gfw_fishing_effort": {
        "sql": """
            SELECT effort_date, lat, lon, hours, flag, vessel_ids,
                   dataset_key, source, loaded_at
            FROM fact_gfw_fishing_effort
            ORDER BY effort_date DESC
            LIMIT :limit
        """,
        "order_col": "effort_date",
        "access": "RESEARCH (GFW terms)",
        "notes": (
            "Powered by Global Fishing Watch — non-commercial use + attribution."
        ),
    },
    "fact_bloom_risk": {
        "sql": """
            SELECT risk_date, region_id, country_id, cell_id, lat, lon,
                   chl_mg_m3, sst_c, sst_anomaly, persistence_days,
                   bloom_probability, risk_level, risk_score,
                   drivers, model_version, disclaimer, created_at
            FROM fact_bloom_risk
            ORDER BY risk_date DESC, bloom_probability DESC
            LIMIT :limit
        """,
        "order_col": "risk_date",
        "access": "RESEARCH",
        "notes": "Heuristic bloom-risk scores (decision-support, not a bloom detection).",
    },
    "dim_regions": {
        "sql": """
            SELECT region_id, region_name, country,
                   min_lon, max_lon, min_lat, max_lat,
                   is_primary, status, created_at
            FROM dim_regions
            ORDER BY is_primary DESC, region_id
            LIMIT :limit
        """,
        "order_col": "region_id",
        "access": "OPEN",
        "notes": "Regional coverage model (Kenya ACTIVE; others PLANNED).",
    },
}


@st.cache_resource
def get_engine():
    return create_engine(DB_URI, pool_pre_ping=True, connect_args={"connect_timeout": 15})


def _is_missing_relation(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "undefinedtable" in msg
        or "does not exist" in msg
        or "undefinedcolumn" in msg
        or "undefined column" in msg
    )


@st.cache_data(ttl=120)
def load_dataset(name: str, limit: int) -> tuple[pd.DataFrame, str | None]:
    """Return (df, error_message). Empty df + message on failure / missing table."""
    cfg = DATASETS[name]
    engine = get_engine()
    try:
        df = pd.read_sql(text(cfg["sql"]), engine, params={"limit": limit})
        return df, None
    except SQLAlchemyError as e:
        return pd.DataFrame(), str(e)
    except Exception as e:
        return pd.DataFrame(), str(e)


@st.cache_data(ttl=300)
def load_table_columns(table: str) -> pd.DataFrame:
    engine = get_engine()
    try:
        return pd.read_sql(
            text(
                """
                SELECT column_name, data_type, ordinal_position
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = :t
                ORDER BY ordinal_position
                """
            ),
            engine,
            params={"t": table},
        )
    except Exception:
        return pd.DataFrame()


dataset = st.selectbox("Dataset", list(DATASETS.keys()))
limit = st.slider("Row limit", min_value=10, max_value=2000, value=100, step=10)
cfg = DATASETS[dataset]

c1, c2 = st.columns(2)
with c1:
    st.markdown(f"**Access:** `{cfg['access']}`")
with c2:
    st.markdown(f"**Notes:** {cfg['notes']}")

df, err = load_dataset(dataset, limit)

if err:
    if _is_missing_relation(err):
        st.warning(
            f"Table or columns for `{dataset}` are not available in the live database. "
            "Run the matching ingestion / seed job, then refresh."
        )
    else:
        st.error(f"Could not load `{dataset}`.")
    st.code(err, language="text")
    st.info("Empty state — no rows shown. No synthetic data is generated here.")
elif df is None or df.empty:
    st.info(
        f"No rows returned for `{dataset}` (limit={limit}). "
        "The table may be empty or filters excluded all rows."
    )
else:
    st.success(f"{len(df):,} rows · {len(df.columns)} columns")
    st.dataframe(df, width="stretch")
    st.download_button(
        "Download CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=f"{dataset}.csv",
        mime="text/csv",
    )

with st.expander("Columns (information_schema)", expanded=False):
    cols_df = load_table_columns(dataset)
    if cols_df.empty:
        st.caption("Could not read information_schema (table missing or DB unreachable).")
    else:
        st.dataframe(cols_df, width="stretch", hide_index=True)

with st.expander("SQL used", expanded=False):
    st.code(cfg["sql"].strip(), language="sql")

st.divider()
st.markdown(
    """
**Data use**
- Research / decision-support extracts only. Not a legal determination.
- GFW effort is apparent fishing effort under GFW non-commercial terms.
- For programmatic access, use the API at `http://localhost:8000/docs`.
"""
)

if close_page is not None:
    close_page(methodology=True, attribution=True)
