"""Phase 15 — Fisheries Intelligence (Kenya EEZ)."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        import os

        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")


st.set_page_config(
    page_title="Fisheries Intelligence",
    page_icon=":material/phishing:",
    layout="wide",
)

try:
    from ow_theme import apply_theme, init_a11y_defaults

    init_a11y_defaults()
    apply_theme()
except Exception:
    pass

st.title("Fisheries Intelligence")
st.caption(
    "Effort · hotspots · seasonality · activity risk heuristics · Kenya EEZ · "
    "Not a legal finding of illegal fishing"
)


def _sa_uri(uri: str) -> str:
    if not uri:
        return uri
    if uri.startswith("postgresql://"):
        return "postgresql+psycopg2://" + uri[len("postgresql://") :]
    if uri.startswith("postgres://"):
        return "postgresql+psycopg2://" + uri[len("postgres://") :]
    return uri


DB = get_db_uri()


@st.cache_data(ttl=45)
def load():
    if not DB:
        err = pd.DataFrame({"error": ["No database URI configured."]})
        return {"risk": err, "hotspots": err, "season": err, "alerts": err, "grid": err}

    eng = create_engine(_sa_uri(DB), pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:  # noqa: BLE001
            return pd.DataFrame({"error": [str(e)]})

    return {
        "risk": q(
            """
            SELECT * FROM fact_illegal_fishing_risk
            ORDER BY created_at DESC NULLS LAST
            LIMIT 5
            """
        ),
        "hotspots": q(
            """
            SELECT * FROM fact_fishing_hotspots
            ORDER BY hotspot_rank ASC NULLS LAST
            LIMIT 50
            """
        ),
        "season": q(
            """
            SELECT * FROM fact_fisheries_seasonality
            ORDER BY month_num ASC
            """
        ),
        "alerts": q(
            """
            SELECT * FROM fact_fisheries_alerts
            ORDER BY created_at DESC NULLS LAST
            LIMIT 50
            """
        ),
        "grid": q(
            """
            SELECT cell_id, lat, lon, SUM(hours) AS hours
            FROM fact_fishing_effort_grid
            GROUP BY 1, 2, 3
            ORDER BY hours DESC
            LIMIT 200
            """
        ),
    }


d = load()

risk_empty = (
    d["risk"] is None
    or d["risk"].empty
    or "error" in d["risk"].columns
)
if risk_empty:
    err = None
    if d["risk"] is not None and not d["risk"].empty and "error" in d["risk"].columns:
        err = d["risk"].iloc[0].get("error")
    st.warning(
        "No Phase 15 data. Run `python ingestion/init_phase15_fisheries.py` and "
        "`python ingestion/run_phase15_fisheries.py`"
        + (f"\n\n({err})" if err else "")
    )
    st.stop()

r = d["risk"].iloc[0]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Risk level", r.get("risk_level", "—"))
c2.metric("Risk score", r.get("risk_score", "—"))
c3.metric("GFW hours", r.get("gfw_hours", "—"))
c4.metric("Confidence", r.get("confidence_score", "—"))

if r.get("drivers"):
    st.caption(f"Drivers: {r['drivers']}")
if r.get("disclaimer"):
    st.info(r["disclaimer"])

st.subheader("Hotspots")
hs = d["hotspots"]
if hs is not None and not hs.empty and "error" not in hs.columns:
    st.dataframe(hs, use_container_width=True, hide_index=True)
    if hs["lat"].notna().any():
        fig = px.scatter(
            hs,
            x="lon",
            y="lat",
            size="total_hours",
            color="intensity_score",
            hover_name="hotspot_rank",
            hover_data=[c for c in ("total_hours", "cell_count") if c in hs.columns],
            title="Fishing effort hotspots (Kenya EEZ)",
            color_continuous_scale="YlOrRd",
        )
        fig.update_yaxes(scaleanchor="x", scaleratio=1)
        st.plotly_chart(fig, use_container_width=True)
else:
    st.caption("No hotspots")

st.subheader("Seasonality")
se = d["season"]
if se is not None and not se.empty and "error" not in se.columns:
    st.dataframe(se, use_container_width=True, hide_index=True)
    if "month_name" in se.columns and "total_hours" in se.columns:
        st.bar_chart(se.set_index("month_name")["total_hours"])
else:
    st.caption("No seasonality rows")

st.subheader("Effort grid (top cells)")
gr = d["grid"]
if gr is not None and not gr.empty and "error" not in gr.columns:
    st.dataframe(gr, use_container_width=True, hide_index=True)
else:
    st.caption("No effort grid")

st.subheader("Fisheries alerts")
al = d["alerts"]
if al is not None and not al.empty and "error" not in al.columns:
    st.dataframe(al, use_container_width=True, hide_index=True)
else:
    st.caption("No open fisheries alerts")

st.caption(
    "Patterns are for human review only. Not a legal determination. "
    "Global Fishing Watch where sourced from GFW extracts."
)
