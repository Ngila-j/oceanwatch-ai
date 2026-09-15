"""Phase 22 — Event Bus viewer."""

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

st.set_page_config(
    page_title="Event Bus",
    page_icon=":material/hub:",
    layout="wide",
)
st.title("Event Bus")
st.caption(
    "Lightweight Postgres-backed event stream — no Kafka required. "
    "Events are published from domain fact tables for UI / alerts / API consumers."
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
        "topics": q("SELECT * FROM event_bus_topics ORDER BY topic"),
        "consumers": q("SELECT * FROM event_bus_consumers ORDER BY consumer_id"),
        "events": q(
            """
            SELECT event_id, topic, event_type, severity, status,
                   region_id, source_table, created_at, model_version, payload
            FROM event_bus
            ORDER BY created_at DESC
            LIMIT 500
            """
        ),
    }


d = load()

if d["events"] is None or d["events"].empty or "error" in d["events"].columns:
    st.warning("No Phase 22 data. Run init_phase22_event_bus.py and run_phase22_event_bus.py")
    if d["events"] is not None and not d["events"].empty:
        st.code(str(d["events"].iloc[0].get("error")))
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Topics", len(d["topics"]) if d["topics"] is not None else 0)
c2.metric("Consumers", len(d["consumers"]) if d["consumers"] is not None else 0)
c3.metric("Events (sample)", len(d["events"]))

st.subheader("Topics")
st.dataframe(d["topics"], width="stretch")

st.subheader("Consumers")
st.dataframe(d["consumers"], width="stretch")

st.subheader("Events")
topics = sorted(d["events"]["topic"].dropna().unique().tolist()) if "topic" in d["events"].columns else []
sel = st.multiselect("Filter topics", topics, default=topics)
view = d["events"]
if sel:
    view = view[view["topic"].isin(sel)]
st.dataframe(view, width="stretch")

if "topic" in view.columns:
    st.bar_chart(view["topic"].value_counts())

st.info(
    "Status PENDING means published and available to consumers. "
    "PROCESSED means the notification engine has consumed the event. "
    "A future dispatcher can refine delivery channels further."
)