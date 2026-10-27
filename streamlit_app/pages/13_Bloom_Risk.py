"""Chlorophyll bloom-risk probability — indicator only, not HAB diagnosis."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        import os

        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")


st.set_page_config(page_title="Bloom Risk", page_icon="🦠", layout="wide")
st.title("Chlorophyll Bloom-Risk Probability")
st.caption(
    "Bloom-risk indicator — not a confirmed harmful algal bloom diagnosis. "
    "Decision-support only; HAB confirmation requires biological sampling."
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
                SELECT * FROM fact_bloom_risk
                ORDER BY risk_date DESC, bloom_probability DESC
                LIMIT 50
                """
            ),
            engine,
        )
        return df, None
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "fact_bloom_risk" in msg or "UndefinedTable" in msg or "does not exist" in msg:
            return (
                pd.DataFrame(),
                "No bloom-risk data yet. Run `python ingestion/ml_bloom_probability.py` "
                "(creates `fact_bloom_risk` and seeds Kenya EEZ cells).",
            )
        return pd.DataFrame(), f"Could not load bloom risk: {e}"


df, err = load()
if err:
    st.warning(err)
    st.stop()

if df is None or df.empty:
    st.info(
        "No bloom-risk rows. Run `python ingestion/ml_bloom_probability.py` to seed "
        "`fact_bloom_risk`."
    )
    st.stop()

# Latest risk_date snapshot
if "risk_date" in df.columns:
    latest_date = df["risk_date"].max()
    latest = df[df["risk_date"] == latest_date].copy()
else:
    latest_date = None
    latest = df.copy()

prob_col = next(
    (c for c in ("bloom_probability", "probability", "risk_score") if c in latest.columns),
    None,
)
level_col = next((c for c in ("risk_level", "level") if c in latest.columns), None)

c1, c2, c3, c4 = st.columns(4)
if prob_col:
    c1.metric("Max probability (latest)", f"{float(latest[prob_col].max()):.0f}%")
    c2.metric("Mean probability (latest)", f"{float(latest[prob_col].mean()):.0f}%")
if level_col and not latest.empty:
    top = latest.sort_values(prob_col, ascending=False).iloc[0] if prob_col else latest.iloc[0]
    c3.metric("Top cell level", str(top.get(level_col, "—")))
    c4.metric("As-of", str(latest_date) if latest_date is not None else "—")
elif latest_date is not None:
    c4.metric("As-of", str(latest_date))

st.subheader("Latest cell risk")
show_cols = [
    c
    for c in (
        "risk_date",
        "cell_id",
        "lat",
        "lon",
        "chl_mg_m3",
        "sst_c",
        "sst_anomaly",
        "persistence_days",
        "bloom_probability",
        "risk_level",
        "drivers",
    )
    if c in latest.columns
]
st.dataframe(
    latest[show_cols].sort_values(prob_col, ascending=False) if prob_col else latest[show_cols],
    use_container_width=True,
    hide_index=True,
)

if prob_col and "risk_date" in df.columns:
    st.subheader("Probability trend (cell mean by day)")
    trend = (
        df.groupby("risk_date", as_index=False)[prob_col]
        .mean()
        .sort_values("risk_date")
        .tail(14)
    )
    st.line_chart(trend.set_index("risk_date")[prob_col])

if "disclaimer" in df.columns and df["disclaimer"].notna().any():
    st.caption(str(df["disclaimer"].dropna().iloc[0]))
else:
    st.caption(
        "Indicator only. Confirming harmful algal blooms requires additional biological sampling."
    )
