"""
Command Center — fused multi-domain ops console.

Mission context, situation snapshot, domain readiness, attention queue,
watchlist, catalog search, and one-click mission pack export.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

try:
    from db_config import get_db_uri
except Exception:  # noqa: BLE001
    def get_db_uri() -> str:
        return os.getenv("OCEANWATCH_DB_URI") or os.getenv("DATABASE_URL") or ""

from components.mission import (
    build_mission_brief_markdown,
    export_watchlist_json,
    get_mission_context,
    render_attention_list,
    render_domain_readiness,
    render_mission_context_controls,
    render_mission_strip,
    render_watchlist_panel,
    search_catalog,
    situation_snapshot,
    snapshot_to_metrics_frame,
)
from components.pagekit import boot, close_page
from components.ui import banner, empty_state, kpi_row

boot(
    "Command Center",
    "Fused multi-domain console — mission context, readiness, attention queue, "
    "watchlist, and exportable mission packs. Decision-support only.",
    kicker="OceanWatch AI · Ops",
    chips=[("FUSION", "primary"), ("WATCHLIST", "info"), ("EXPORT", "neutral")],
    icon="🎛️",
)

ctx = render_mission_context_controls(compact=False, key_prefix="cmd")
render_mission_strip(ctx)

uri = (get_db_uri() or "").strip()
if not uri:
    banner(
        "Database URI missing",
        "Set OCEANWATCH_DB_URI (or Streamlit secrets) to load live fusion metrics.",
        tone="warning",
        icon="⚠️",
    )
    engine = None
else:
    raw = uri
    if raw.startswith("postgresql://"):
        raw = raw.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql+psycopg2://", 1)
    connect_args = {"connect_timeout": 15}
    if "supabase" in raw or "pooler" in raw:
        connect_args["sslmode"] = "require"
    try:
        engine = create_engine(
            raw, pool_pre_ping=True, connect_args=connect_args, pool_size=1, max_overflow=0
        )
    except Exception as e:  # noqa: BLE001
        banner("Engine error", str(e), tone="danger", icon="⛔")
        engine = None

snap = situation_snapshot(engine, ctx) if engine is not None else {
    "generated_at": "",
    "posture": "UNKNOWN",
    "metrics": {},
    "domains": {},
    "attention": [],
    "freshness": {},
}

posture = snap.get("posture", "UNKNOWN")
posture_tone = {
    "CALM": "success",
    "WATCH": "warning",
    "HEIGHTENED": "danger",
}.get(posture, "info")

banner(
    f"Operational posture · {posture}",
    f"Region {ctx.get('region')} · lookback {ctx.get('lookback_h')}h · "
    f"severity floor {ctx.get('severity_min')} · focus {ctx.get('focus')}. "
    "Scores are heuristic readiness — not official threat levels.",
    tone=posture_tone,
    icon="🛰️" if posture == "CALM" else ("👀" if posture == "WATCH" else "🚨"),
)

m = snap.get("metrics") or {}
kpi_row(
    [
        {
            "label": "Events",
            "value": f"{int(m.get('events', 0)):,}",
            "hint": f"Last {ctx.get('lookback_h', 24)}h on bus",
            "tone": "primary",
        },
        {
            "label": "Open alerts",
            "value": f"{int(m.get('alerts_open', 0)):,}",
            "hint": "Operational alert rows",
            "tone": "warning" if int(m.get("alerts_open", 0)) else "success",
        },
        {
            "label": "Elevated risk",
            "value": f"{int(m.get('risk_elevated', 0)):,}",
            "hint": "High / critical unified risk",
            "tone": "danger" if int(m.get("risk_elevated", 0)) else "success",
        },
        {
            "label": "Notify backlog",
            "value": f"{int(m.get('notifications_pending', 0)):,}",
            "hint": "Pending / failed deliveries",
            "tone": "warning" if int(m.get("notifications_pending", 0)) else "success",
        },
        {
            "label": "Anomalies",
            "value": f"{int(m.get('anomalies', 0)):,}",
            "hint": "Vessel anomaly hits in window",
            "tone": "info",
        },
        {
            "label": "Trust sources",
            "value": f"{int(m.get('sources', 0)):,}",
            "hint": "Catalogued data sources",
            "tone": "info",
        },
    ]
)

st.markdown("### Domain readiness")
st.caption("Heuristic 0–100 scores from live table fullness — guides where to investigate next.")
render_domain_readiness(snap)

left, right = st.columns([1.25, 1])

with left:
    st.markdown("### Attention queue")
    st.caption("Newest events (fallback: notifications), filtered by severity floor when possible.")
    if engine is None:
        empty_state("No database", "Connect Postgres to populate the attention queue.", icon="🔌")
    else:
        render_attention_list(snap, limit=10)

    st.markdown("### Data freshness")
    fresh = snap.get("freshness") or {}
    if not any(fresh.values()):
        st.caption("No freshness timestamps available yet.")
    else:
        fres_rows = [{"feed": k, "latest": v or "—"} for k, v in fresh.items()]
        st.dataframe(pd.DataFrame(fres_rows), hide_index=True, use_container_width=True)

with right:
    render_watchlist_panel(editable=True, key_prefix="cmdwl")

    st.markdown("### Mission pack export")
    brief_md = build_mission_brief_markdown(snap, ctx)
    st.download_button(
        "Download mission pack (.md)",
        data=brief_md.encode("utf-8"),
        file_name=f"oceanwatch_mission_pack_{ctx.get('region','ALL')}.md",
        mime="text/markdown",
        type="primary",
        use_container_width=True,
    )
    metrics_df = snapshot_to_metrics_frame(snap)
    st.download_button(
        "Download metrics (.csv)",
        data=metrics_df.to_csv(index=False).encode("utf-8"),
        file_name="oceanwatch_mission_metrics.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.download_button(
        "Download watchlist (.json)",
        data=export_watchlist_json().encode("utf-8"),
        file_name="oceanwatch_watchlist.json",
        mime="application/json",
        use_container_width=True,
    )
    with st.expander("Preview mission pack"):
        st.markdown(brief_md)

st.markdown("---")
st.markdown("### Domain finder")
st.caption(
    "Search the product map. Open the matching page from the sidebar "
    "(Streamlit multipage navigation is sidebar-driven)."
)
q = st.text_input(
    "Find a capability",
    placeholder="e.g. bloom, AIS, risk, catalog, dark…",
    key="cmd_find",
)
hits = search_catalog(q)
if not hits:
    st.warning("No matching domains — try a shorter term.")
else:
    # group by domain
    by_dom: dict[str, list] = {}
    for h in hits:
        by_dom.setdefault(h["domain"], []).append(h)
    cols = st.columns(min(3, max(1, len(by_dom))))
    for i, (dom, items) in enumerate(sorted(by_dom.items())):
        with cols[i % len(cols)]:
            st.markdown(f"**{dom}**")
            for it in items:
                st.markdown(
                    f"""
                    <div class="ow-find-hit">
                      <strong>{it['title']}</strong>
                      <span>{it['hint']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

st.markdown("### Investigate next")
st.caption("Persona-aware guidance — use the sidebar to open the page.")
focus = str(ctx.get("focus") or "balanced")
suggestions = {
    "balanced": [
        ("Unified Risk", "Cross-domain elevated tiers"),
        ("Event Bus", "Trace signals into notifications"),
        ("Kenya EEZ Today", "Daily EEZ picture"),
        ("System Health", "Confirm pipelines are green"),
    ],
    "maritime": [
        ("AIS Live", "Vessel picture"),
        ("Dark Activity", "AIS gaps and rendezvous"),
        ("Port Intelligence", "Port calls & congestion"),
        ("Anomaly Engine", "Elevated vessel signals"),
    ],
    "ocean": [
        ("Ocean State", "SST / conditions"),
        ("Bloom Risk", "Ocean color risk"),
        ("WIO Intelligence Index", "Composite index"),
        ("AI Forecasts", "Model outlook"),
    ],
    "risk": [
        ("Operational Alerts", "Open alert queue"),
        ("Unified Risk", "Tiered risk rows"),
        ("Anomaly Engine", "Vessel anomalies"),
        ("Notifications", "Delivery backlog"),
    ],
}
sug = suggestions.get(focus, suggestions["balanced"])
scols = st.columns(4)
for col, (title, hint) in zip(scols, sug):
    col.markdown(
        f"""
        <div class="ow-tile" role="listitem">
          <strong>{title}</strong>
          <span>{hint}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

close_page(methodology=True, attribution=True)
