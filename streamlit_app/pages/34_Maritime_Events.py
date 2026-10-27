"""Phase 19 — Maritime events & vessel state."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

try:
    from db_config import get_db_uri
except ImportError:

    def get_db_uri():
        import os

        return (
            os.getenv("OCEANWATCH_DB_URI")
            or os.getenv("DATABASE_URL")
        )


st.set_page_config(
    page_title="Maritime Events",
    page_icon=":material/radar:",
    layout="wide",
)

try:
    from ow_theme import apply_theme, init_a11y_defaults

    init_a11y_defaults()
    apply_theme()
except Exception:
    pass

st.title("Maritime Events")
st.caption(
    "Vessel state · movements · detected events — patterns for review only, "
    "not legal findings"
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
        return {"state": err, "events": err, "moves": err}

    eng = create_engine(_sa_uri(DB), pool_pre_ping=True)

    def q(sql):
        try:
            return pd.read_sql(text(sql), eng)
        except Exception as e:  # noqa: BLE001
            return pd.DataFrame({"error": [str(e)]})

    return {
        "state": q(
            "SELECT * FROM fact_vessel_state ORDER BY updated_at DESC NULLS LAST"
        ),
        "events": q(
            """
            SELECT * FROM fact_vessel_events
            ORDER BY event_time DESC NULLS LAST
            LIMIT 300
            """
        ),
        "moves": q(
            "SELECT * FROM fact_vessel_movements ORDER BY positions_count DESC"
        ),
    }


d = load()

if d["state"] is None or d["state"].empty or "error" in d["state"].columns:
    err = None
    if d["state"] is not None and not d["state"].empty and "error" in d["state"].columns:
        err = d["state"].iloc[0].get("error")
    st.warning(
        "No Phase 19 data. Run `python ingestion/init_phase19_maritime.py` and "
        "`python ingestion/run_phase19_maritime_events.py`"
        + (f"\n\n({err})" if err else "")
    )
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Vessels (state)", len(d["state"]))
c2.metric("Open event rows", len(d["events"]) if d["events"] is not None and "error" not in d["events"].columns else 0)
c3.metric("Movement rows", len(d["moves"]) if d["moves"] is not None and "error" not in d["moves"].columns else 0)
if "loitering_flag" in d["state"].columns:
    c4.metric(
        "Loitering flags",
        int(d["state"]["loitering_flag"].fillna(False).astype(bool).sum()),
    )
else:
    c4.metric("Loitering flags", "—")

st.subheader("Vessel state")
st.dataframe(d["state"], use_container_width=True, hide_index=True)

if "last_lat" in d["state"].columns and d["state"]["last_lat"].notna().any():
    fig = px.scatter(
        d["state"].dropna(subset=["last_lat", "last_lon"]),
        x="last_lon",
        y="last_lat",
        color="state_label" if "state_label" in d["state"].columns else None,
        hover_name="vessel_name" if "vessel_name" in d["state"].columns else None,
        hover_data=[c for c in ("mmsi", "last_sog", "source") if c in d["state"].columns],
        title="Latest vessel state positions",
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, use_container_width=True)

st.subheader("Events")
if d["events"] is not None and not d["events"].empty and "error" not in d["events"].columns:
    st.dataframe(d["events"], use_container_width=True, hide_index=True)
    if "event_type" in d["events"].columns:
        st.bar_chart(d["events"]["event_type"].value_counts())
else:
    st.caption("No events")

st.subheader("Movements summary")
if d["moves"] is not None and not d["moves"].empty and "error" not in d["moves"].columns:
    st.dataframe(d["moves"], use_container_width=True, hide_index=True)
else:
    st.caption("No movement aggregates")

st.info(
    "OceanWatch identifies patterns requiring review; an anomaly or event score "
    "is not proof of illegal activity."
)
