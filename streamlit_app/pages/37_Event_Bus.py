"""Phase 22 — Event Bus viewer.

Operational console for the Postgres-backed domain event stream
(no Kafka). Shows topic registry, consumers, backlog health, and
filterable event history with payload inspection.
"""

from __future__ import annotations

import json
from typing import Optional

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Event Bus",
    page_icon=":material/hub:",
    layout="wide",
)

st.title("Event Bus")
st.caption(
    "Lightweight Postgres-backed domain event stream — no Kafka required. "
    "Producers publish from fact tables; consumers (UI, notifications, API) read PENDING rows."
)

try:
    from components.branding import attribution_footer, methodology_blurb
except Exception:  # pragma: no cover - optional chrome
    def attribution_footer():  # type: ignore
        pass

    def methodology_blurb():  # type: ignore
        pass


try:
    from components.data_access import has_error, load_event_bus_bundle
except Exception as exc:  # pragma: no cover
    st.error(f"Data access layer unavailable: {exc}")
    st.stop()


@st.cache_data(ttl=45, show_spinner="Loading event bus…")
def _load(limit: int = 500) -> dict:
    return load_event_bus_bundle(limit=limit)


def _safe_int(val, default: int = 0) -> int:
    try:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return default
        return int(val)
    except Exception:
        return default


def _parse_payload(raw) -> Optional[dict]:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, dict):
        return raw
    text = str(raw).strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else {"value": obj}
    except Exception:
        return {"raw": text[:2000]}


def _first_error(*frames: pd.DataFrame) -> Optional[str]:
    for df in frames:
        if has_error(df):
            return str(df.iloc[0].get("error", "unknown error"))
    return None


# ----- sidebar controls -----
with st.sidebar:
    st.header("Filters")
    limit = st.select_slider(
        "Event sample size",
        options=[100, 250, 500, 1000, 2000],
        value=500,
    )
    auto = st.toggle("Auto-refresh cache", value=True, help="Uses 45s TTL cache when on")
    if st.button("Refresh now", use_container_width=True):
        _load.clear()
        st.rerun()

if not auto:
    # Bust cache key subtly by not using cached path when toggled off
    data = load_event_bus_bundle(limit=limit)
else:
    data = _load(limit=limit)

topics_df = data.get("topics", pd.DataFrame())
consumers_df = data.get("consumers", pd.DataFrame())
events_df = data.get("events", pd.DataFrame())
stats_df = data.get("stats", pd.DataFrame())
by_topic_df = data.get("by_topic", pd.DataFrame())
by_sev_df = data.get("by_severity", pd.DataFrame())

err = _first_error(topics_df, consumers_df, events_df, stats_df)
schema_missing = err is not None and any(
    token in err.lower()
    for token in ("does not exist", "undefinedtable", "relation", "event_bus")
)

if schema_missing or (
    (events_df is None or events_df.empty)
    and (topics_df is None or topics_df.empty or has_error(topics_df))
):
    st.warning(
        "No Phase 22 event bus data yet. Initialise and publish:\n\n"
        "```bash\n"
        "python ingestion/init_phase22_event_bus.py\n"
        "python ingestion/run_phase22_event_bus.py\n"
        "```"
    )
    if err:
        with st.expander("Diagnostics"):
            st.code(err)
    st.stop()

# ----- KPI strip -----
stats = stats_df.iloc[0].to_dict() if stats_df is not None and not stats_df.empty and not has_error(stats_df) else {}
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Topics", _safe_int(stats.get("topic_n"), len(topics_df) if topics_df is not None else 0))
c2.metric("Consumers", len(consumers_df) if consumers_df is not None and not has_error(consumers_df) else 0)
c3.metric("Pending", _safe_int(stats.get("pending")))
c4.metric("Processed", _safe_int(stats.get("processed")))
c5.metric("Total events", _safe_int(stats.get("total_events"), len(events_df) if events_df is not None else 0))

latest = stats.get("latest_at")
if latest is not None and not (isinstance(latest, float) and pd.isna(latest)):
    st.caption(f"Latest publish: **{latest}** · model `phase22_bus_v1.1` · append-only (idempotent by `source_key`)")

# ----- main tabs -----
tab_stream, tab_topics, tab_consumers, tab_health = st.tabs(
    ["Event stream", "Topics", "Consumers", "Backlog health"]
)

with tab_stream:
    working = events_df.copy() if events_df is not None and not has_error(events_df) else pd.DataFrame()

    if working.empty:
        st.info("Event bus is initialised but has no rows yet. Run `run_phase22_event_bus.py`.")
    else:
        # Normalise filter columns
        if "topic" not in working.columns:
            working["topic"] = None
        if "status" not in working.columns:
            working["status"] = None
        if "severity" not in working.columns:
            working["severity"] = None

        f1, f2, f3, f4 = st.columns([2, 1.2, 1.2, 1.5])
        topic_opts = sorted(working["topic"].dropna().astype(str).unique().tolist())
        status_opts = sorted(working["status"].dropna().astype(str).str.upper().unique().tolist())
        sev_opts = sorted(working["severity"].dropna().astype(str).str.upper().unique().tolist())

        with f1:
            sel_topics = st.multiselect("Topics", topic_opts, default=topic_opts)
        with f2:
            sel_status = st.multiselect(
                "Status",
                status_opts,
                default=status_opts,
            )
        with f3:
            sel_sev = st.multiselect("Severity", sev_opts, default=sev_opts)
        with f4:
            query = st.text_input("Search type / source / payload", "")

        view = working
        if sel_topics:
            view = view[view["topic"].astype(str).isin(sel_topics)]
        if sel_status:
            view = view[view["status"].astype(str).str.upper().isin([s.upper() for s in sel_status])]
        if sel_sev:
            view = view[view["severity"].astype(str).str.upper().isin([s.upper() for s in sel_sev])]
        if query.strip():
            q = query.strip().lower()
            mask = (
                view.get("event_type", pd.Series(dtype=str)).astype(str).str.lower().str.contains(q, na=False)
                | view.get("source_table", pd.Series(dtype=str)).astype(str).str.lower().str.contains(q, na=False)
                | view.get("payload", pd.Series(dtype=str)).astype(str).str.lower().str.contains(q, na=False)
            )
            view = view[mask]

        st.caption(f"Showing **{len(view)}** of **{len(working)}** sampled events")

        display_cols = [
            c
            for c in [
                "created_at",
                "topic",
                "event_type",
                "severity",
                "status",
                "source_table",
                "region_id",
                "event_id",
            ]
            if c in view.columns
        ]
        st.dataframe(
            view[display_cols] if display_cols else view,
            width="stretch",
            hide_index=True,
        )

        # Charts
        ch1, ch2 = st.columns(2)
        with ch1:
            st.subheader("By topic")
            if "topic" in view.columns and not view.empty:
                st.bar_chart(view["topic"].value_counts())
            else:
                st.caption("No topic data")
        with ch2:
            st.subheader("By severity")
            if "severity" in view.columns and not view.empty:
                st.bar_chart(view["severity"].astype(str).str.upper().value_counts())
            else:
                st.caption("No severity data")

        # Payload inspector
        st.subheader("Payload inspector")
        if "event_id" in view.columns and not view.empty:
            ids = view["event_id"].tolist()
            labels = {
                eid: (
                    f"{eid} · {view.loc[view['event_id'] == eid, 'topic'].iloc[0] if 'topic' in view.columns else '?'} · "
                    f"{view.loc[view['event_id'] == eid, 'event_type'].iloc[0] if 'event_type' in view.columns else '?'}"
                )
                for eid in ids[:200]
            }
            chosen = st.selectbox(
                "Select event",
                options=list(labels.keys()),
                format_func=lambda i: labels.get(i, str(i)),
            )
            row = view.loc[view["event_id"] == chosen].iloc[0]
            m1, m2, m3 = st.columns(3)
            m1.write(f"**Status:** {row.get('status')}")
            m2.write(f"**Source:** {row.get('source_table')}")
            m3.write(f"**Key:** `{row.get('source_key')}`")
            payload = _parse_payload(row.get("payload"))
            if payload is None:
                st.info("No payload on this event.")
            else:
                st.json(payload)
        else:
            st.caption("No events available to inspect.")

with tab_topics:
    if topics_df is None or topics_df.empty or has_error(topics_df):
        st.info("No topics registered.")
        if has_error(topics_df):
            st.code(str(topics_df.iloc[0].get("error")))
    else:
        st.dataframe(topics_df, width="stretch", hide_index=True)
        if by_topic_df is not None and not by_topic_df.empty and not has_error(by_topic_df):
            st.subheader("Volume by topic")
            st.dataframe(by_topic_df, width="stretch", hide_index=True)

with tab_consumers:
    if consumers_df is None or consumers_df.empty or has_error(consumers_df):
        st.info("No consumers registered.")
        if has_error(consumers_df):
            st.code(str(consumers_df.iloc[0].get("error")))
    else:
        st.dataframe(consumers_df, width="stretch", hide_index=True)
        st.caption(
            "Consumers are logical subscribers. Phase 23 `alert_dispatcher` drains PENDING "
            "ops/fisheries/risk topics into the notification queue."
        )

with tab_health:
    h1, h2 = st.columns(2)
    with h1:
        st.subheader("Status backlog")
        if stats:
            backlog = pd.DataFrame(
                [
                    {"status": "PENDING", "n": _safe_int(stats.get("pending"))},
                    {"status": "PROCESSED", "n": _safe_int(stats.get("processed"))},
                    {
                        "status": "OTHER/TOTAL",
                        "n": max(
                            0,
                            _safe_int(stats.get("total_events"))
                            - _safe_int(stats.get("pending"))
                            - _safe_int(stats.get("processed")),
                        ),
                    },
                ]
            )
            st.dataframe(backlog, width="stretch", hide_index=True)
            if _safe_int(stats.get("pending")) > 200:
                st.warning(
                    "Large PENDING backlog — run `python ingestion/run_phase23_notifications.py` "
                    "or inspect failed consumers."
                )
            elif _safe_int(stats.get("pending")) == 0:
                st.success("No PENDING events — bus is drained or idle.")
        else:
            st.caption("Stats unavailable")
    with h2:
        st.subheader("Severity mix (all-time sample)")
        if by_sev_df is not None and not by_sev_df.empty and not has_error(by_sev_df):
            st.dataframe(by_sev_df, width="stretch", hide_index=True)
            if "severity" in by_sev_df.columns and "n" in by_sev_df.columns:
                st.bar_chart(by_sev_df.set_index("severity")["n"])
        else:
            st.caption("No severity aggregates")

st.info(
    "**PENDING** = published and available to consumers. "
    "**PROCESSED** = notification engine (or another consumer) has acknowledged the event. "
    "Publishes are **idempotent** via `source_key` — re-running the publisher will not duplicate rows."
)

try:
    methodology_blurb()
    attribution_footer()
except Exception:
    pass
