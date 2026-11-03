"""Phase 22 — Event Bus viewer.

Operational console for the Postgres-backed domain event stream
(no Kafka). Topic registry, consumers, backlog health, and filterable
event history with payload inspection.
"""

from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from components.data_access import has_error, load_event_bus_bundle
from components.pagekit import boot, close_page
from components.ui import banner, empty_state, kpi_row, section

boot(
    "Event Bus",
    "Postgres-backed domain event stream for OceanWatch pipelines. "
    "Trace signals from producers into consumers and the notification queue.",
    kicker="Operations fabric · Phase 22",
    chips=[
        ("No Kafka", "info"),
        ("Idempotent publish", "primary"),
    ],
    page_title="Event Bus · OceanWatch",
    icon="🔗",
)

with st.sidebar:
    st.markdown("### Event Bus tools")
    limit = st.slider(
        "Event row limit",
        min_value=50,
        max_value=2000,
        value=500,
        step=50,
        help="Caps history fetch for performance.",
    )
    if st.button("Refresh event bus", use_container_width=True, type="primary"):
        load_event_bus_bundle.clear() if hasattr(load_event_bus_bundle, "clear") else None
        st.cache_data.clear()
        st.rerun()


@st.cache_data(ttl=45, show_spinner="Loading event bus…")
def _bundle(limit: int) -> dict[str, pd.DataFrame]:
    return load_event_bus_bundle(limit=limit)


data = _bundle(limit)
topics = data.get("topics", pd.DataFrame())
consumers = data.get("consumers", pd.DataFrame())
events = data.get("events", pd.DataFrame())
by_status = data.get("by_status", pd.DataFrame())
by_topic = data.get("by_topic", pd.DataFrame())
by_severity = data.get("by_severity", pd.DataFrame())

# Schema / connectivity guard
schema_error = None
for frame in (topics, consumers, events):
    if has_error(frame):
        schema_error = str(frame.iloc[0].get("error"))
        break

if schema_error and any(
    token in schema_error.lower()
    for token in ("does not exist", "undefinedtable", "relation ", "undefined table", "connect")
):
    banner(
        "Event Bus tables not ready",
        "Initialise and publish Phase 22, then refresh this page.",
        tone="warning",
        icon="⚠️",
    )
    st.code(
        "python ingestion/init_phase22_event_bus.py\n"
        "python ingestion/run_phase22_event_bus.py",
        language="bash",
    )
    with st.expander("Diagnostics", expanded=False):
        st.code(schema_error)
    close_page()
    st.stop()


def _count(df: pd.DataFrame) -> int:
    if df is None or df.empty or has_error(df):
        return 0
    return int(len(df))


_PENDING = {"PENDING", "QUEUED", "NEW", "FAILED", "RETRY", "ERROR"}
pending_n = 0
if not by_status.empty and not has_error(by_status):
    cols = {c.lower(): c for c in by_status.columns}
    status_col = cols.get("status")
    count_col = cols.get("n") or cols.get("count") or cols.get("events")
    if status_col and count_col:
        mask = by_status[status_col].astype(str).str.upper().isin(_PENDING)
        try:
            pending_n = int(by_status.loc[mask, count_col].sum())
        except Exception:
            pending_n = 0
if pending_n == 0 and events is not None and not events.empty and not has_error(events):
    sc = next((c for c in events.columns if c.lower() == "status"), None)
    if sc:
        pending_n = int(events[sc].astype(str).str.upper().isin(_PENDING).sum())

kpi_row(
    [
        {
            "label": "Topics",
            "value": f"{_count(topics):,}",
            "hint": "Active topic definitions.",
            "tone": "primary",
        },
        {
            "label": "Consumers",
            "value": f"{_count(consumers):,}",
            "hint": "Registered event consumers.",
            "tone": "info",
        },
        {
            "label": "Events loaded",
            "value": f"{_count(events):,}",
            "hint": f"Recent events loaded for this page (limit {limit}).",
            "tone": "primary",
        },
        {
            "label": "Backlog",
            "value": f"{pending_n:,}",
            "hint": "Statuses that still need consumer attention.",
            "tone": "danger" if pending_n else "success",
        },
    ]
)

if pending_n > 200:
    banner(
        f"{pending_n} events still pending",
        "Re-run notification drain or check consumer lag: "
        "`python ingestion/run_phase23_notifications.py`",
        tone="warning",
        icon="⏳",
    )

tab_events, tab_health, tab_registry = st.tabs(
    ["Event history", "Backlog health", "Registry"]
)

with tab_events:
    section("Filterable history", "Slice by topic, severity, status, and free text.")
    if events is None or events.empty or has_error(events):
        empty_state(
            "No events yet",
            "Publish from live facts: `python ingestion/run_phase22_event_bus.py`",
            icon="📭",
        )
    else:
        f1, f2, f3, f4 = st.columns([1.2, 1, 1, 1.4])
        with f1:
            topic_opts = ["(all)"]
            if "topic" in events.columns:
                topic_opts += sorted(
                    {str(x) for x in events["topic"].dropna().unique().tolist()}
                )
            topic_sel = st.selectbox("Topic", topic_opts, index=0)
        with f2:
            sev_opts = ["(all)"]
            if "severity" in events.columns:
                sev_opts += sorted(
                    {str(x) for x in events["severity"].dropna().unique().tolist()}
                )
            sev_sel = st.selectbox("Severity", sev_opts, index=0)
        with f3:
            st_opts = ["(all)"]
            if "status" in events.columns:
                st_opts += sorted(
                    {str(x) for x in events["status"].dropna().unique().tolist()}
                )
            st_sel = st.selectbox("Status", st_opts, index=0)
        with f4:
            query = st.text_input(
                "Search",
                placeholder="event_type, source_key, title…",
            )

        view = events.copy()
        if topic_sel != "(all)" and "topic" in view.columns:
            view = view[view["topic"].astype(str) == topic_sel]
        if sev_sel != "(all)" and "severity" in view.columns:
            view = view[view["severity"].astype(str) == sev_sel]
        if st_sel != "(all)" and "status" in view.columns:
            view = view[view["status"].astype(str) == st_sel]
        if query:
            q = query.strip().lower()
            text_cols = [
                c
                for c in (
                    "event_type",
                    "source_table",
                    "source_key",
                    "topic",
                    "payload",
                    "region_id",
                    "country_id",
                    "title",
                    "message",
                )
                if c in view.columns
            ]
            if text_cols:
                mask = False
                for c in text_cols:
                    mask = mask | view[c].astype(str).str.lower().str.contains(q, na=False)
                view = view[mask]

        st.caption(f"Showing **{len(view):,}** of **{len(events):,}** loaded events.")
        if "source_table" in events.columns and (
            events["source_table"].astype(str).str.lower() == "demo"
        ).any():
            st.caption(
                "Includes diagnostic demo events from Phase 22 seed — "
                "re-run run_phase22_event_bus.py to publish from live facts."
            )
        prefer_cols = [
            c
            for c in (
                "created_at",
                "topic",
                "event_type",
                "severity",
                "status",
                "title",
                "message",
                "source_table",
                "source_key",
                "region_id",
                "event_id",
            )
            if c in view.columns
        ]
        other = [c for c in view.columns if c not in prefer_cols and c != "payload"]
        display = view[prefer_cols + other] if prefer_cols else view
        st.dataframe(display, use_container_width=True, hide_index=True)

        with st.expander("Inspect payload", expanded=False):
            if view.empty or "event_id" not in view.columns:
                st.caption("Select a filtered row with an event_id to inspect payload.")
            else:
                ids = view["event_id"].astype(str).tolist()
                pick = st.selectbox("Event ID", ids, index=0)
                row = view[view["event_id"].astype(str) == pick].iloc[0]
                meta_cols = st.columns(4)
                for i, key in enumerate(("topic", "event_type", "severity", "status")):
                    if key in row.index:
                        meta_cols[i].markdown(f"**{key}**  \n{row[key]}")
                payload = row.get("payload")
                if payload is None or (isinstance(payload, float) and pd.isna(payload)):
                    st.caption("No payload column for this row.")
                else:
                    try:
                        if isinstance(payload, str):
                            parsed: Any = json.loads(payload)
                        else:
                            parsed = payload
                        st.json(parsed)
                    except Exception:
                        st.code(str(payload))

with tab_health:
    section("Backlog health", "Status, topic, and severity mix for the loaded window.")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**By status**")
        if by_status is None or by_status.empty or has_error(by_status):
            empty_state("No status rollup", icon="—")
        else:
            st.dataframe(by_status, use_container_width=True, hide_index=True)
            if "status" in by_status.columns and "n" in by_status.columns:
                st.bar_chart(by_status.set_index("status")["n"])
    with c2:
        st.markdown("**By topic**")
        if by_topic is None or by_topic.empty or has_error(by_topic):
            empty_state("No topic rollup", icon="—")
        else:
            st.dataframe(by_topic, use_container_width=True, hide_index=True)
            if "topic" in by_topic.columns and "n" in by_topic.columns:
                st.bar_chart(by_topic.set_index("topic")["n"])
    with c3:
        st.markdown("**By severity**")
        if by_severity is None or by_severity.empty or has_error(by_severity):
            empty_state("No severity rollup", icon="—")
        else:
            st.dataframe(by_severity, use_container_width=True, hide_index=True)
            if "severity" in by_severity.columns and "n" in by_severity.columns:
                st.bar_chart(by_severity.set_index("severity")["n"])

with tab_registry:
    section("Topics & consumers", "What can publish, and who is subscribed.")
    left, right = st.columns(2)
    with left:
        st.markdown("**Topics**")
        if topics is None or topics.empty or has_error(topics):
            empty_state("No topics registered", icon="📑")
        else:
            st.dataframe(topics, use_container_width=True, hide_index=True)
    with right:
        st.markdown("**Consumers**")
        if consumers is None or consumers.empty or has_error(consumers):
            empty_state("No consumers registered", icon="🔌")
        else:
            st.dataframe(consumers, use_container_width=True, hide_index=True)

banner(
    "Durable by design",
    "Publish is idempotent on source_key. Schema init uses CREATE IF NOT EXISTS "
    "with soft migrations — re-running jobs will not wipe the bus.",
    tone="info",
    icon="ℹ️",
)

close_page()
