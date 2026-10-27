"""Mombasa Port Operational Risk."""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL")


st.set_page_config(
    page_title="Port Operational Risk",
    page_icon=":material/anchor:",
    layout="wide",
)

try:
    from ow_theme import apply_theme, init_a11y_defaults

    init_a11y_defaults()
    apply_theme()
except Exception:
    pass

st.title("Mombasa Port Operational Risk")
st.caption("Traffic · tide · congestion composite · decision support only")


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
        return pd.DataFrame(), pd.DataFrame(), "No database URI configured."

    eng = create_engine(_sa_uri(DB), pool_pre_ping=True)
    try:
        risk = pd.read_sql(
            text("SELECT * FROM fact_port_risk ORDER BY risk_date DESC LIMIT 5"),
            eng,
        )
    except Exception as e:  # noqa: BLE001
        return pd.DataFrame(), pd.DataFrame(), str(e)

    try:
        metrics = pd.read_sql(
            text("SELECT * FROM fact_port_metrics ORDER BY metric_date DESC LIMIT 3"),
            eng,
        )
    except Exception:  # noqa: BLE001
        metrics = pd.DataFrame()

    return risk, metrics, None


risk, metrics, err = load()

if err or risk is None or risk.empty:
    msg = (
        "No port risk data. Run `python ingestion/seed_port_activity.py` then "
        "`python ingestion/ml_port_risk.py`."
    )
    if err:
        # Hide noisy internal SQL if it's simply missing relation
        low = str(err).lower()
        if "does not exist" in low or "undefinedtable" in low:
            msg += "\n\n(`fact_port_risk` is missing on the connected database.)"
        else:
            msg += f"\n\n({err})"
    st.warning(msg)
    st.stop()

r = risk.iloc[0]


def _f(key, default=None):
    v = r.get(key, default)
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return default
    return v


c1, c2, c3, c4 = st.columns(4)
comp = _f("composite_risk")
c1.metric("Composite Risk", f"{float(comp):.1f}" if comp is not None else "—")
c2.metric("Risk Level", _f("risk_level", "—"))
ts = _f("traffic_score")
c3.metric("Traffic Score", f"{float(ts):.1f}" if ts is not None else "—")
td = _f("tide_score")
c4.metric("Tide Score", f"{float(td):.1f}" if td is not None else "—")

drivers = _f("drivers") or ""
level = str(_f("risk_level") or "").upper()
if level == "HIGH":
    st.error(f"**HIGH operational risk** — {drivers}")
elif level == "MODERATE":
    st.warning(f"**MODERATE risk** — {drivers}")
else:
    st.success(f"**{level or 'LOW'} risk** — {drivers}")

st.subheader("Score breakdown")
st.dataframe(risk, use_container_width=True, hide_index=True)

if metrics is not None and not metrics.empty:
    st.subheader("Latest port metrics")
    st.dataframe(metrics, use_container_width=True, hide_index=True)

st.caption("Heuristic decision-support only — not a legal or regulatory determination.")
