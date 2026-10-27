"""Phase 17 — Data Catalog & Trust."""

from __future__ import annotations

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:
    import os
    from pathlib import Path

    def get_db_uri() -> str:
        env_path = Path(__file__).resolve().parents[2] / "ingestion" / ".env"
        if env_path.exists():
            for raw in env_path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line.startswith("OCEANWATCH_DB_URI="):
                    return line.split("=", 1)[1].strip().strip("'").strip('"')
        return (
            os.getenv("OCEANWATCH_DB_URI")
            or os.getenv("DATABASE_URL")
            or "postgresql://postgres:password@localhost:5433/oceanwatch_db"
        )


try:
    from components.pagekit import boot, close_page

    boot(
        "Data Catalog & Trust",
        "Sources, products, licenses, quality, lineage, and ingestion runs.",
        kicker="Data & trust",
        icon="📚",
    )
except Exception:
    st.set_page_config(page_title="Data Catalog & Trust", page_icon="📚", layout="wide")
    st.title("📚 Data Catalog & Trust")

st.caption(
    "Phase 17 catalog. GFW layers remain CC BY-NC; SAMPLE products are not operational."
)


@st.cache_resource(show_spinner=False)
def _engine():
    return create_engine(
        get_db_uri(), pool_pre_ping=True, connect_args={"connect_timeout": 20}
    )


def q(sql: str) -> pd.DataFrame:
    try:
        with _engine().connect() as conn:
            return pd.read_sql(text(sql), conn)
    except Exception as e:
        st.warning(f"Query unavailable: {e}")
        return pd.DataFrame()


tabs = st.tabs(
    [
        "Sources",
        "Products",
        "Licenses",
        "Quality",
        "Lineage",
        "Ingestion runs",
    ]
)

with tabs[0]:
    st.subheader("Data sources")
    df = q("SELECT * FROM dim_data_sources ORDER BY provider, dataset_name")
    if df.empty:
        st.info(
            "No rows in `dim_data_sources`. Run `python ingestion/init_phase17_trust.py` "
            "then `python ingestion/run_phase17_trust.py`."
        )
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[1]:
    st.subheader("Data products")
    df = q("SELECT * FROM dim_data_products ORDER BY product_id")
    if df.empty:
        st.info("No rows in `dim_data_products`. Seed Phase 17 trust catalog.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("Licenses")
    df = q("SELECT * FROM dim_data_licenses ORDER BY license_code")
    if df.empty:
        st.info("No rows in `dim_data_licenses`.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.caption(
            "GFW fishing effort uses **CC BY-NC 4.0** (non-commercial + attribution). "
            "SAMPLE / proprietary demo layers have explicit redistribution restrictions."
        )

with tabs[3]:
    st.subheader("Quality scores")
    df = q("SELECT * FROM fact_data_quality_scores ORDER BY computed_at DESC")
    if df.empty:
        st.info("No rows in `fact_data_quality_scores`.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[4]:
    st.subheader("Lineage")
    df = q(
        "SELECT * FROM fact_data_lineage ORDER BY product_id, upstream_product_id"
    )
    if df.empty:
        st.info("No rows in `fact_data_lineage`.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

with tabs[5]:
    st.subheader("Recent ingestion runs")
    df = q(
        "SELECT * FROM fact_ingestion_runs ORDER BY started_at DESC LIMIT 200"
    )
    if df.empty:
        st.info("No rows in `fact_ingestion_runs`.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()
st.markdown(
    "**Trust notes:** Heuristic quality grades support operations dashboards only. "
    "GFW CC BY-NC products require attribution and non-commercial handling. "
    "SAMPLE layers must stay labeled and are not enforcement-grade."
)

try:
    close_page()
except Exception:
    pass
