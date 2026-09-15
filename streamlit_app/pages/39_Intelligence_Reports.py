"""Phase 24 — Automated intelligence reports."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Intelligence Reports",
    page_icon=":material/description:",
    layout="wide",
)
st.title("Intelligence Reports")
st.caption(
    "Automated Daily Operational Brief and Weekly Ocean Brief — generated from live OceanWatch facts"
)

DB = "postgresql://postgres:password@localhost:5433/oceanwatch_db"


@st.cache_data(ttl=45)
def load():
    eng = create_engine(DB, pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:
            return pd.DataFrame({"error": [str(e)]})

    return {
        "types": q("SELECT * FROM dim_report_types ORDER BY report_type_id"),
        "runs": q(
            """
            SELECT * FROM fact_report_runs
            ORDER BY generated_at DESC
            LIMIT 20
            """
        ),
        "sections": q(
            """
            SELECT * FROM fact_report_sections
            ORDER BY run_id, section_order
            """
        ),
    }


d = load()

if d["runs"] is None or d["runs"].empty or "error" in d["runs"].columns:
    st.warning("No Phase 24 data. Run init_phase24_reports.py and run_phase24_reports.py")
    st.stop()

st.subheader("Report types")
st.dataframe(d["types"], width="stretch")

st.subheader("Recent runs")
st.dataframe(d["runs"], width="stretch")

run_ids = d["runs"]["run_id"].tolist()
labels = {
    int(r.run_id): f"{r.report_type_id} · {r.report_date} · {r.title}"
    for r in d["runs"].itertuples()
}
choice = st.selectbox(
    "Open report",
    options=run_ids,
    format_func=lambda x: labels.get(int(x), str(x)),
)

run = d["runs"][d["runs"]["run_id"] == choice].iloc[0]
st.markdown(f"### {run['title']}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Overall", run.get("overall_status"))
c2.metric("Confidence", run.get("confidence_score"))
c3.metric("Sections", run.get("section_count"))
c4.metric("Region", run.get("region_id"))
st.write(run.get("summary"))
st.caption(f"Model: {run.get('model_version')} · generated {run.get('generated_at')}")

secs = d["sections"][d["sections"]["run_id"] == choice].sort_values("section_order")
for _, s in secs.iterrows():
    with st.expander(f"{int(s['section_order'])}. {s['section_title']} — {s['status']}", expanded=True):
        m1, m2 = st.columns(2)
        m1.metric("Value", s.get("metric_value"), s.get("metric_label"))
        m2.metric("Status", s.get("status"))
        st.write(s.get("narrative"))
        st.caption(f"Evidence: {s.get('evidence')}")

st.info(
    "Reports are decision-support snapshots, not official government notices. "
    "PDF export can be layered later on the same fact_report_* tables."
)