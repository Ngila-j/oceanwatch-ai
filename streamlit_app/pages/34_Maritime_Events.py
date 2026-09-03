"""Phase 19 — Maritime events & vessel state."""

import streamlit as st
import pandas as pd
import plotly.express as px
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Maritime Events",
    page_icon=":material/radar:",
    layout="wide",
)
st.title("Maritime Events")
st.caption(
    "Vessel state · movements · detected events — patterns for review only, "
    "not legal findings"
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
    st.warning("No Phase 19 data. Run init_phase19_maritime.py and run_phase19_maritime_events.py")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Vessels (state)", len(d["state"]))
c2.metric("Open event rows", len(d["events"]) if d["events"] is not None else 0)
c3.metric("Movement rows", len(d["moves"]) if d["moves"] is not None else 0)
if "state_label" in d["state"].columns:
    c4.metric(
        "Loitering flags",
        int(d["state"]["loitering_flag"].fillna(False).astype(bool).sum())
        if "loitering_flag" in d["state"].columns
        else 0,
    )
else:
    c4.metric("Loitering flags", "—")

st.subheader("Vessel state")
st.dataframe(d["state"], width="stretch")

if (
    "last_lat" in d["state"].columns
    and d["state"]["last_lat"].notna().any()
):
    fig = px.scatter(
        d["state"].dropna(subset=["last_lat", "last_lon"]),
        x="last_lon",
        y="last_lat",
        color="state_label",
        hover_name="vessel_name",
        hover_data=["mmsi", "last_sog", "source"],
        title="Latest vessel state positions",
    )
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    st.plotly_chart(fig, width="stretch")

st.subheader("Events")
if d["events"] is not None and not d["events"].empty and "error" not in d["events"].columns:
    st.dataframe(d["events"], width="stretch")
    if "event_type" in d["events"].columns:
        st.bar_chart(d["events"]["event_type"].value_counts())
else:
    st.caption("No events")

st.subheader("Movements summary")
if d["moves"] is not None and not d["moves"].empty and "error" not in d["moves"].columns:
    st.dataframe(d["moves"], width="stretch")
else:
    st.caption("No movement aggregates")

st.info(
    "OceanWatch identifies patterns requiring review; an anomaly or event score "
    "is not proof of illegal activity."
)