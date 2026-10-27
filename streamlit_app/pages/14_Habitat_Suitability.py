"""Predicted habitat suitability from SST / CHL — not fish presence."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        import os

        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")


st.set_page_config(page_title="Habitat Suitability", page_icon="🐠", layout="wide")
st.title("Predicted Habitat Suitability")
st.caption(
    "Based on available SST and chlorophyll features — not a prediction of where fish are. "
    "Decision-support environmental suitability proxy only."
)


@st.cache_data(ttl=120)
def load():
    uri = get_db_uri()
    if not uri:
        return pd.DataFrame(), "No database URI configured."
    if uri.startswith("postgresql://"):
        uri = "postgresql+psycopg2://" + uri[len("postgresql://") :]
    elif uri.startswith("postgres://"):
        uri = "postgresql+psycopg2://" + uri[len("postgres://") :]
    engine = create_engine(uri, pool_pre_ping=True)
    try:
        df = pd.read_sql(
            text(
                """
                SELECT * FROM fact_habitat_suitability
                ORDER BY as_of_date DESC, suitability_score DESC NULLS LAST
                LIMIT 50
                """
            ),
            engine,
        )
        return df, None
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "fact_habitat_suitability" in msg or "UndefinedTable" in msg or "does not exist" in msg:
            return (
                pd.DataFrame(),
                "No habitat suitability data yet. Run `python ingestion/ml_habitat_suitability.py` "
                "(creates `fact_habitat_suitability` and seeds Kenya EEZ cells).",
            )
        return pd.DataFrame(), f"Could not load habitat suitability: {e}"


df, err = load()
if err:
    st.warning(err)
    st.stop()

if df is None or df.empty:
    st.info(
        "No habitat suitability rows. Run `python ingestion/ml_habitat_suitability.py` to seed "
        "`fact_habitat_suitability`."
    )
    st.stop()

score_col = next(
    (c for c in ("suitability_score", "habitat_score", "score") if c in df.columns),
    None,
)
class_col = next(
    (c for c in ("suitability_class", "class", "label") if c in df.columns),
    None,
)

if "as_of_date" in df.columns:
    latest_date = df["as_of_date"].max()
    latest = df[df["as_of_date"] == latest_date].copy()
else:
    latest_date = None
    latest = df.copy()

c1, c2, c3, c4 = st.columns(4)
if score_col and not latest.empty:
    c1.metric("Max suitability (latest)", f"{float(latest[score_col].max()):.0f}")
    c2.metric("Mean suitability (latest)", f"{float(latest[score_col].mean()):.0f}")
    top = latest.sort_values(score_col, ascending=False).iloc[0]
    if class_col:
        c3.metric("Top class", str(top.get(class_col, "—")))
    c4.metric("As-of", str(latest_date) if latest_date is not None else "—")
elif latest_date is not None:
    c4.metric("As-of", str(latest_date))

st.subheader("Latest cells")
show_cols = [
    c
    for c in (
        "as_of_date",
        "cell_id",
        "region",
        "lat",
        "lon",
        "sst_celsius",
        "chlorophyll_mg_m3",
        "suitability_score",
        "habitat_score",
        "suitability_class",
        "thermal_fit",
        "productivity_fit",
        "notes",
    )
    if c in latest.columns
]
view = latest[show_cols]
if score_col and score_col in view.columns:
    view = view.sort_values(score_col, ascending=False)
st.dataframe(view, use_container_width=True, hide_index=True)

if score_col and "as_of_date" in df.columns:
    st.subheader("Suitability trend (cell mean by day)")
    trend = (
        df.groupby("as_of_date", as_index=False)[score_col]
        .mean()
        .sort_values("as_of_date")
        .tail(14)
    )
    st.line_chart(trend.set_index("as_of_date")[score_col])

st.caption(
    "Environmental suitability from SST/CHL features only. "
    "Not a prediction of fish presence, catch, or stock abundance."
)
