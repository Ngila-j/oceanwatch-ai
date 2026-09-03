"""Phase 17 — Data Catalog & Trust."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Data Catalog",
    page_icon=":material/library_books:",
    layout="wide",
)
st.title("Data Catalog & Trust")
st.caption(
    "Sources · products · licenses · quality · lineage · ingestion runs — "
    "free to access is not the same as free to redistribute"
)

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=60)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "sources": q(
            "SELECT * FROM dim_data_sources ORDER BY provider, dataset_name"
        ),
        "products": q("SELECT * FROM dim_data_products ORDER BY product_id"),
        "licenses": q("SELECT * FROM dim_data_licenses ORDER BY license_code"),
        "quality": q(
            "SELECT * FROM fact_data_quality ORDER BY as_of_date DESC, product_id"
        ),
        "lineage": q("SELECT * FROM fact_data_lineage ORDER BY lineage_id"),
        "runs": q(
            """
            SELECT * FROM fact_data_ingestion_runs
            ORDER BY finished_at DESC NULLS LAST
            LIMIT 100
            """
        ),
    }


d = load()

if d["sources"] is None or d["sources"].empty or "error" in d["sources"].columns:
    st.warning("No Phase 17 data. Run init_phase17_trust.py and run_phase17_trust.py")
    if d["sources"] is not None and not d["sources"].empty:
        st.code(str(d["sources"].iloc[0].get("error")))
    st.stop()

avg_q = None
if d["quality"] is not None and not d["quality"].empty and "error" not in d["quality"].columns:
    avg_q = float(d["quality"]["quality_score"].mean())

c1, c2, c3, c4 = st.columns(4)
c1.metric("Sources", len(d["sources"]))
c2.metric("Products", len(d["products"]) if d["products"] is not None else 0)
c3.metric("Licenses", len(d["licenses"]) if d["licenses"] is not None else 0)
c4.metric("Avg quality", round(avg_q, 1) if avg_q is not None else "—")

st.subheader("Data sources")
st.dataframe(d["sources"], width="stretch")

st.subheader("Data products")
st.dataframe(d["products"], width="stretch")

st.subheader("Licenses")
st.dataframe(d["licenses"], width="stretch")

st.subheader("Quality scores")
if d["quality"] is not None and not d["quality"].empty and "error" not in d["quality"].columns:
    st.dataframe(d["quality"], width="stretch")
else:
    st.caption("No quality rows")

st.subheader("Lineage")
if d["lineage"] is not None and not d["lineage"].empty and "error" not in d["lineage"].columns:
    st.dataframe(d["lineage"], width="stretch")
else:
    st.caption("No lineage rows")

st.subheader("Recent ingestion runs")
if d["runs"] is not None and not d["runs"].empty and "error" not in d["runs"].columns:
    st.dataframe(d["runs"], width="stretch")
else:
    st.caption("No ingestion runs")

st.info(
    "Always check license_code and access_type before republishing or commercial use. "
    "GFW and sample layers have explicit restrictions."
)