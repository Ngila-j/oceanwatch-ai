"""
Mission context, watchlist, situation fusion, and briefing export.

Shared across Home, Command Center, and the app shell so operators keep
one coherent view of region / lookback / severity while jumping domains.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import pandas as pd
import streamlit as st

# ── Catalog (sidebar-friendly labels → operator guidance) ────────────────────

PAGE_CATALOG: list[dict[str, str]] = [
    {"id": "home", "title": "Home", "domain": "Cockpit", "hint": "Mission snapshot & shortcuts"},
    {"id": "eez", "title": "Kenya EEZ Today", "domain": "Situation", "hint": "Daily EEZ picture"},
    {"id": "exec", "title": "Executive Summary", "domain": "Situation", "hint": "Leadership brief"},
    {"id": "ais", "title": "AIS Live", "domain": "Maritime", "hint": "Vessel positions"},
    {"id": "port", "title": "Port Intelligence", "domain": "Maritime", "hint": "Port calls & congestion"},
    {"id": "port_risk", "title": "Port Risk", "domain": "Maritime", "hint": "Port risk scores"},
    {"id": "fish", "title": "Fishing Activity", "domain": "Maritime", "hint": "Fishing pressure"},
    {"id": "gfw", "title": "GFW Fishing Effort", "domain": "Maritime", "hint": "Global Fishing Watch"},
    {"id": "dark", "title": "Dark Activity", "domain": "Maritime", "hint": "AIS gaps & rendezvous"},
    {"id": "anomaly", "title": "Anomaly Engine", "domain": "Risk", "hint": "Elevated vessel signals"},
    {"id": "unified", "title": "Unified Risk", "domain": "Risk", "hint": "Cross-domain risk tiers"},
    {"id": "alerts", "title": "Operational Alerts", "domain": "Risk", "hint": "Live alert queue"},
    {"id": "bus", "title": "Event Bus", "domain": "Ops", "hint": "Signal → notification trace"},
    {"id": "notify", "title": "Notifications", "domain": "Ops", "hint": "Delivery backlog"},
    {"id": "subs", "title": "Alert Subscriptions", "domain": "Ops", "hint": "Routing rules"},
    {"id": "sst", "title": "Ocean State", "domain": "Ocean", "hint": "SST / ocean conditions"},
    {"id": "bloom", "title": "Bloom Risk", "domain": "Ocean", "hint": "Ocean color / blooms"},
    {"id": "habitat", "title": "Habitat Suitability", "domain": "Ocean", "hint": "Species habitat scores"},
    {"id": "wio", "title": "WIO Intelligence Index", "domain": "Ocean", "hint": "Composite WIO index"},
    {"id": "forecast", "title": "AI Forecasts", "domain": "Ocean", "hint": "Model forecasts"},
    {"id": "regions", "title": "Regional Coverage", "domain": "Coverage", "hint": "Countries / EEZ hierarchy"},
    {"id": "catalog", "title": "Data Catalog", "domain": "Trust", "hint": "Sources · licenses · lineage"},
    {"id": "health", "title": "System Health", "domain": "Platform", "hint": "DB · API · jobs"},
    {"id": "reports", "title": "Intelligence Reports", "domain": "Intel", "hint": "Automated reports"},
    {"id": "brief", "title": "Weekly Ocean Brief", "domain": "Intel", "hint": "Narrative weekly pack"},
    {"id": "playback", "title": "Historical Playback", "domain": "Intel", "hint": "Time-travel views"},
    {"id": "cmd", "title": "Command Center", "domain": "Cockpit", "hint": "Fused ops console"},
]

REGIONS = [
    ("ALL", "All coverage"),
    ("KE", "Kenya (ACTIVE)"),
    ("TZ", "Tanzania (planned)"),
    ("SC", "Seychelles (planned)"),
    ("MZ", "Mozambique (planned)"),
    ("WIO", "Western Indian Ocean"),
]

LOOKBACK_OPTIONS = [6, 12, 24, 48, 72, 168]  # hours
SEVERITY_OPTIONS = ["all", "info", "low", "medium", "high", "critical"]

_WATCHLIST_KEY = "ow_watchlist"
_CTX_KEY = "ow_mission_ctx"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def default_mission_context() -> dict[str, Any]:
    return {
        "region": "KE",
        "lookback_h": 24,
        "severity_min": "all",
        "operator_callsign": "",
        "focus": "balanced",  # balanced | maritime | ocean | risk
    }


def get_mission_context() -> dict[str, Any]:
    if _CTX_KEY not in st.session_state:
        st.session_state[_CTX_KEY] = default_mission_context()
    # ensure keys
    base = default_mission_context()
    cur = st.session_state[_CTX_KEY]
    for k, v in base.items():
        cur.setdefault(k, v)
    return cur


def set_mission_context(**kwargs: Any) -> dict[str, Any]:
    ctx = get_mission_context()
    ctx.update({k: v for k, v in kwargs.items() if v is not None})
    st.session_state[_CTX_KEY] = ctx
    return ctx


def get_watchlist() -> list[dict[str, Any]]:
    if _WATCHLIST_KEY not in st.session_state:
        st.session_state[_WATCHLIST_KEY] = []
    return st.session_state[_WATCHLIST_KEY]


def add_watch_item(
    *,
    kind: str,
    key: str,
    label: str,
    note: str = "",
    meta: Optional[dict[str, Any]] = None,
) -> bool:
    """Add item if not already present. Returns True if added."""
    wl = get_watchlist()
    kind = (kind or "note").strip().lower()
    key = (key or label or "").strip()
    if not key:
        return False
    for item in wl:
        if item.get("kind") == kind and str(item.get("key")) == key:
            return False
    wl.append(
        {
            "kind": kind,
            "key": key,
            "label": label or key,
            "note": note or "",
            "meta": meta or {},
            "added_at": _now_utc().isoformat(),
        }
    )
    st.session_state[_WATCHLIST_KEY] = wl
    return True


def remove_watch_item(kind: str, key: str) -> None:
    wl = get_watchlist()
    st.session_state[_WATCHLIST_KEY] = [
        i for i in wl if not (i.get("kind") == kind and str(i.get("key")) == str(key))
    ]


def clear_watchlist() -> None:
    st.session_state[_WATCHLIST_KEY] = []


def render_mission_context_controls(*, compact: bool = False, key_prefix: str = "mc") -> dict[str, Any]:
    """Sidebar / page mission filters. Writes session state."""
    ctx = get_mission_context()
    region_ids = [r[0] for r in REGIONS]
    region_labels = {r[0]: r[1] for r in REGIONS}

    if compact:
        c1, c2, c3 = st.columns(3)
        with c1:
            region = st.selectbox(
                "Region",
                region_ids,
                index=region_ids.index(ctx.get("region", "KE"))
                if ctx.get("region", "KE") in region_ids
                else 0,
                format_func=lambda x: region_labels.get(x, x),
                key=f"{key_prefix}_region",
            )
        with c2:
            lookback = st.selectbox(
                "Lookback (h)",
                LOOKBACK_OPTIONS,
                index=LOOKBACK_OPTIONS.index(int(ctx.get("lookback_h", 24)))
                if int(ctx.get("lookback_h", 24)) in LOOKBACK_OPTIONS
                else 2,
                key=f"{key_prefix}_lb",
            )
        with c3:
            sev = st.selectbox(
                "Min severity",
                SEVERITY_OPTIONS,
                index=SEVERITY_OPTIONS.index(str(ctx.get("severity_min", "all")))
                if str(ctx.get("severity_min", "all")) in SEVERITY_OPTIONS
                else 0,
                key=f"{key_prefix}_sev",
            )
        focus = ctx.get("focus", "balanced")
        callsign = ctx.get("operator_callsign", "")
    else:
        c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1.2])
        with c1:
            region = st.selectbox(
                "Coverage region",
                region_ids,
                index=region_ids.index(ctx.get("region", "KE"))
                if ctx.get("region", "KE") in region_ids
                else 0,
                format_func=lambda x: region_labels.get(x, x),
                key=f"{key_prefix}_region",
                help="Soft filter for fusion queries and briefings.",
            )
        with c2:
            lookback = st.selectbox(
                "Lookback window",
                LOOKBACK_OPTIONS,
                index=LOOKBACK_OPTIONS.index(int(ctx.get("lookback_h", 24)))
                if int(ctx.get("lookback_h", 24)) in LOOKBACK_OPTIONS
                else 2,
                format_func=lambda h: f"{h}h" if h < 168 else "7d",
                key=f"{key_prefix}_lb",
            )
        with c3:
            sev = st.selectbox(
                "Severity floor",
                SEVERITY_OPTIONS,
                index=SEVERITY_OPTIONS.index(str(ctx.get("severity_min", "all")))
                if str(ctx.get("severity_min", "all")) in SEVERITY_OPTIONS
                else 0,
                key=f"{key_prefix}_sev",
            )
        with c4:
            focus = st.selectbox(
                "Focus mode",
                ["balanced", "maritime", "ocean", "risk"],
                index=["balanced", "maritime", "ocean", "risk"].index(
                    ctx.get("focus", "balanced")
                )
                if ctx.get("focus", "balanced") in ("balanced", "maritime", "ocean", "risk")
                else 0,
                key=f"{key_prefix}_focus",
            )
        callsign = st.text_input(
            "Operator callsign (optional)",
            value=ctx.get("operator_callsign", ""),
            key=f"{key_prefix}_call",
            placeholder="e.g. OW-OPS-1",
            help="Stamped onto exported mission packs.",
        )

    return set_mission_context(
        region=region,
        lookback_h=int(lookback),
        severity_min=sev,
        focus=focus,
        operator_callsign=callsign or "",
    )


def render_mission_strip(ctx: Optional[dict[str, Any]] = None) -> None:
    """Compact HTML strip summarizing active mission context."""
    ctx = ctx or get_mission_context()
    region_labels = {r[0]: r[1] for r in REGIONS}
    reg = region_labels.get(ctx.get("region", "KE"), ctx.get("region", "KE"))
    lb = int(ctx.get("lookback_h", 24))
    lb_s = f"{lb}h" if lb < 168 else "7d"
    sev = str(ctx.get("severity_min", "all"))
    focus = str(ctx.get("focus", "balanced"))
    call = (ctx.get("operator_callsign") or "").strip()
    call_bit = f'<span class="ow-chip ow-chip-info">{_esc(call)}</span>' if call else ""
    st.markdown(
        f"""
        <div class="ow-mission-strip" role="status" aria-label="Mission context">
          <span class="ow-mission-kicker">Mission context</span>
          <span class="ow-chip ow-chip-primary">{_esc(reg)}</span>
          <span class="ow-chip ow-chip-neutral">Lookback { _esc(lb_s) }</span>
          <span class="ow-chip ow-chip-neutral">Severity ≥ { _esc(sev) }</span>
          <span class="ow-chip ow-chip-info">Focus · { _esc(focus) }</span>
          {call_bit}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _esc(s: Any) -> str:
    from html import escape

    return escape(str(s if s is not None else ""))


def search_catalog(query: str) -> list[dict[str, str]]:
    q = (query or "").strip().lower()
    if not q:
        return list(PAGE_CATALOG)
    out = []
    for p in PAGE_CATALOG:
        blob = f"{p['title']} {p['domain']} {p['hint']} {p['id']}".lower()
        if q in blob:
            out.append(p)
    return out


def _scalar(engine, sql: str, default: int = 0) -> int:
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            v = conn.execute(text(sql)).scalar()
            return int(v or 0)
    except Exception:
        return default


def _df(engine, sql: str) -> pd.DataFrame:
    try:
        from sqlalchemy import text

        with engine.connect() as conn:
            return pd.read_sql(text(sql), conn)
    except Exception:
        return pd.DataFrame()


def situation_snapshot(engine, ctx: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """
    Multi-domain fused counts for Home / Command Center / API.
    Best-effort: missing tables → 0 / empty.
    """
    ctx = ctx or get_mission_context()
    hours = int(ctx.get("lookback_h", 24) or 24)
    sev = str(ctx.get("severity_min", "all") or "all").lower()

    # Severity filter fragments (soft)
    sev_rank = {"all": 0, "info": 1, "low": 2, "medium": 3, "high": 4, "critical": 5}
    min_rank = sev_rank.get(sev, 0)

    snap: dict[str, Any] = {
        "generated_at": _now_utc().isoformat(),
        "region": ctx.get("region", "ALL"),
        "lookback_h": hours,
        "severity_min": sev,
        "metrics": {},
        "freshness": {},
        "attention": [],
        "domains": {},
    }

    metrics = snap["metrics"]
    freshness = snap["freshness"]

    metrics["events"] = _scalar(
        engine,
        f"""
        SELECT COUNT(*) FROM fact_events
        WHERE COALESCE(created_at, event_time, ts) >= NOW() - INTERVAL '{hours} hours'
        """,
    )
    metrics["notifications_pending"] = _scalar(
        engine,
        """
        SELECT COUNT(*) FROM fact_notifications
        WHERE LOWER(COALESCE(status,'')) IN ('pending','queued','failed','retry')
        """,
    )
    metrics["alerts_open"] = _scalar(
        engine,
        f"""
        SELECT COUNT(*) FROM fact_operational_alerts
        WHERE LOWER(COALESCE(status,'open')) IN ('open','active','new')
           OR COALESCE(created_at, alert_time) >= NOW() - INTERVAL '{hours} hours'
        """,
    )
    metrics["risk_elevated"] = _scalar(
        engine,
        """
        SELECT COUNT(*) FROM unified_risk
        WHERE LOWER(COALESCE(tier, risk_level, '')) IN ('high','critical','severe')
        """,
    )
    metrics["anomalies"] = _scalar(
        engine,
        f"""
        SELECT COUNT(*) FROM fact_vessel_anomalies
        WHERE COALESCE(detected_at, ts, created_at) >= NOW() - INTERVAL '{hours} hours'
        """,
    )
    metrics["vessels_sample"] = _scalar(
        engine,
        """
        SELECT COUNT(DISTINCT COALESCE(mmsi::text, vessel_id::text, ship_id::text))
        FROM fact_ais_positions
        """,
    )
    metrics["ports_watched"] = _scalar(engine, "SELECT COUNT(*) FROM dim_ports_ref")
    metrics["countries"] = _scalar(engine, "SELECT COUNT(*) FROM dim_countries")
    metrics["sources"] = _scalar(engine, "SELECT COUNT(*) FROM dim_data_sources")

    # Freshness probes (latest timestamps)
    probes = [
        ("events", "SELECT MAX(COALESCE(created_at, event_time, ts)) FROM fact_events"),
        ("ais", "SELECT MAX(COALESCE(ts, base_date_time, created_at)) FROM fact_ais_positions"),
        ("alerts", "SELECT MAX(COALESCE(created_at, alert_time)) FROM fact_operational_alerts"),
        ("risk", "SELECT MAX(COALESCE(as_of, updated_at, created_at)) FROM unified_risk"),
        ("wio", "SELECT MAX(index_date) FROM fact_wio_index"),
        ("ingestion", "SELECT MAX(COALESCE(finished_at, started_at)) FROM fact_ingestion_runs"),
    ]
    for name, sql in probes:
        try:
            from sqlalchemy import text

            with engine.connect() as conn:
                v = conn.execute(text(sql)).scalar()
                freshness[name] = v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)
        except Exception:
            freshness[name] = None

    # Attention queue (newest events / notifications)
    attn = _df(
        engine,
        f"""
        SELECT
          COALESCE(event_type, topic, 'event') AS title,
          COALESCE(severity, 'info') AS severity,
          COALESCE(created_at, event_time, ts) AS ts,
          COALESCE(summary, payload::text, '') AS detail
        FROM fact_events
        WHERE COALESCE(created_at, event_time, ts) >= NOW() - INTERVAL '{hours} hours'
        ORDER BY ts DESC NULLS LAST
        LIMIT 12
        """,
    )
    if attn.empty:
        attn = _df(
            engine,
            f"""
            SELECT
              COALESCE(title, channel, 'notification') AS title,
              COALESCE(severity, status, 'info') AS severity,
              COALESCE(created_at, updated_at) AS ts,
              COALESCE(body, message, '') AS detail
            FROM fact_notifications
            ORDER BY ts DESC NULLS LAST
            LIMIT 12
            """,
        )

    rows_attn: list[dict[str, Any]] = []
    if not attn.empty:
        for _, r in attn.iterrows():
            s = str(r.get("severity") or "info").lower()
            if min_rank and sev_rank.get(s, 1) < min_rank:
                continue
            rows_attn.append(
                {
                    "title": str(r.get("title") or "item"),
                    "severity": s,
                    "ts": r.get("ts").isoformat() if hasattr(r.get("ts"), "isoformat") else str(r.get("ts") or ""),
                    "detail": str(r.get("detail") or "")[:240],
                }
            )
    snap["attention"] = rows_attn[:10]

    # Domain readiness heuristic
    snap["domains"] = {
        "maritime": {
            "score": min(100, metrics["vessels_sample"] * 2 + metrics["anomalies"] * 5),
            "label": "Maritime",
            "ok": metrics["vessels_sample"] > 0 or metrics["anomalies"] > 0,
        },
        "risk": {
            "score": min(100, metrics["risk_elevated"] * 10 + metrics["alerts_open"] * 5),
            "label": "Risk & alerts",
            "ok": True,
        },
        "ops": {
            "score": min(100, metrics["events"] * 3 + (10 if metrics["notifications_pending"] == 0 else 4)),
            "label": "Event bus / notify",
            "ok": metrics["events"] > 0 or metrics["notifications_pending"] == 0,
        },
        "trust": {
            "score": min(100, metrics["sources"] * 8 + metrics["countries"] * 10),
            "label": "Catalog & coverage",
            "ok": metrics["sources"] > 0 or metrics["countries"] > 0,
        },
    }

    # Overall posture
    elevated = metrics["risk_elevated"] + metrics["alerts_open"] + metrics["notifications_pending"]
    if elevated >= 10:
        posture = "HEIGHTENED"
    elif elevated >= 1:
        posture = "WATCH"
    else:
        posture = "CALM"
    snap["posture"] = posture
    return snap


def build_mission_brief_markdown(snap: dict[str, Any], ctx: Optional[dict[str, Any]] = None) -> str:
    ctx = ctx or get_mission_context()
    wl = get_watchlist()
    m = snap.get("metrics") or {}
    lines = [
        f"# OceanWatch Mission Pack",
        f"",
        f"- **Generated (UTC):** {snap.get('generated_at', _now_utc().isoformat())}",
        f"- **Region:** {ctx.get('region', 'ALL')}",
        f"- **Lookback:** {ctx.get('lookback_h', 24)}h",
        f"- **Severity floor:** {ctx.get('severity_min', 'all')}",
        f"- **Focus:** {ctx.get('focus', 'balanced')}",
        f"- **Operator:** {ctx.get('operator_callsign') or '—'}",
        f"- **Posture:** **{snap.get('posture', 'UNKNOWN')}**",
        f"",
        f"## Metrics",
        f"| Metric | Value |",
        f"|--------|------:|",
    ]
    for k, v in m.items():
        lines.append(f"| {k.replace('_', ' ')} | {v} |")

    lines += ["", "## Domain readiness", "| Domain | Score | OK |", "|--------|------:|:--:|"]
    for d in (snap.get("domains") or {}).values():
        lines.append(f"| {d.get('label')} | {d.get('score')} | {'yes' if d.get('ok') else 'no'} |")

    lines += ["", "## Attention queue"]
    attn = snap.get("attention") or []
    if not attn:
        lines.append("_Queue clear or tables not populated._")
    else:
        for a in attn:
            lines.append(
                f"- **[{a.get('severity','info')}]** {a.get('title')} — {a.get('ts','')}"
                f"  \n  {a.get('detail','')}"
            )

    lines += ["", "## Watchlist"]
    if not wl:
        lines.append("_Empty — pin vessels, ports, or notes from Command Center._")
    else:
        for w in wl:
            lines.append(
                f"- **{w.get('kind')}** `{w.get('key')}` — {w.get('label')}"
                + (f" · {w.get('note')}" if w.get("note") else "")
            )

    lines += [
        "",
        "## Freshness",
        "| Feed | Latest |",
        "|------|--------|",
    ]
    for k, v in (snap.get("freshness") or {}).items():
        lines.append(f"| {k} | {v or '—'} |")

    # Operator notebook (session)
    notes = []
    try:
        notes = list(st.session_state.get("ow_operator_notes") or [])
    except Exception:
        notes = []
    lines += ["", "## Operator notebook"]
    if not notes:
        lines.append("_No session notes._")
    else:
        for n in notes[:20]:
            lines.append(f"### {n.get('title', 'Note')}")
            lines.append(f"*{n.get('ts', '')}* · {', '.join(n.get('tags') or [])}")
            lines.append(n.get("body") or "")
            lines.append("")

    lines += [
        "",
        "---",
        "_Decision-support only — not an official authority product. "
        "Validate critical actions against primary sources._",
        "",
    ]
    return "\n".join(lines)


def render_watchlist_panel(*, editable: bool = True, key_prefix: str = "wl") -> None:
    wl = get_watchlist()
    st.markdown("#### Operator watchlist")
    if not wl:
        st.caption("No pinned items yet. Add vessels, ports, regions, or freeform notes below.")
    else:
        for i, item in enumerate(list(wl)):
            cols = st.columns([2, 2, 3, 1] if editable else [2, 2, 4])
            cols[0].markdown(f"**{item.get('kind', 'note')}**")
            cols[1].code(str(item.get("key", "")), language=None)
            cols[2].write(item.get("label") or "")
            if editable and cols[3].button("✕", key=f"{key_prefix}_rm_{i}", help="Remove"):
                remove_watch_item(str(item.get("kind")), str(item.get("key")))
                st.rerun()
            if item.get("note"):
                st.caption(item["note"])

    if editable:
        with st.expander("Add watch item", expanded=not wl):
            a1, a2, a3 = st.columns(3)
            kind = a1.selectbox(
                "Kind",
                ["vessel", "port", "region", "event", "note"],
                key=f"{key_prefix}_kind",
            )
            key = a2.text_input("Key / ID", key=f"{key_prefix}_key", placeholder="MMSI / port code / …")
            label = a3.text_input("Label", key=f"{key_prefix}_label", placeholder="Display name")
            note = st.text_input("Note", key=f"{key_prefix}_note", placeholder="Why watching?")
            b1, b2 = st.columns(2)
            if b1.button("Pin to watchlist", type="primary", key=f"{key_prefix}_add"):
                ok = add_watch_item(kind=kind, key=key, label=label or key, note=note)
                if ok:
                    st.success("Pinned.")
                    st.rerun()
                else:
                    st.warning("Already on watchlist or missing key.")
            if b2.button("Clear all", key=f"{key_prefix}_clear") and wl:
                clear_watchlist()
                st.rerun()


def render_domain_readiness(snap: dict[str, Any]) -> None:
    domains = snap.get("domains") or {}
    if not domains:
        return
    cols = st.columns(len(domains))
    for col, (k, d) in zip(cols, domains.items()):
        score = int(d.get("score") or 0)
        ok = bool(d.get("ok"))
        tone = "success" if ok and score >= 20 else ("warning" if ok else "danger")
        col.markdown(
            f"""
            <div class="ow-domain-card" data-tone="{tone}">
              <div class="ow-domain-label">{_esc(d.get('label') or k)}</div>
              <div class="ow-domain-score">{score}</div>
              <div class="ow-domain-hint">{'Ready' if ok else 'Needs data'}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_attention_list(snap: dict[str, Any], *, limit: int = 8) -> None:
    attn = (snap.get("attention") or [])[:limit]
    if not attn:
        st.info("Attention queue is clear (or event/notification tables are empty).")
        return
    for a in attn:
        sev = str(a.get("severity") or "info")
        st.markdown(
            f"""
            <div class="ow-attn-row" data-sev="{_esc(sev)}">
              <span class="ow-attn-sev">{_esc(sev)}</span>
              <div>
                <strong>{_esc(a.get('title'))}</strong>
                <div class="ow-attn-meta">{_esc(a.get('ts'))}</div>
                <div class="ow-attn-detail">{_esc(a.get('detail'))}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def snapshot_to_metrics_frame(snap: dict[str, Any]) -> pd.DataFrame:
    m = snap.get("metrics") or {}
    return pd.DataFrame([{"metric": k, "value": v} for k, v in m.items()])


def export_watchlist_json() -> str:
    return json.dumps(get_watchlist(), indent=2, default=str)
