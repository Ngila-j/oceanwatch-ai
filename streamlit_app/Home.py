"""
OceanWatch AI — Home (multi-domain operator cockpit)

Situation pulse · domain mosaic · attention queue · port focus ·
persona launchpad · intelligence brief · data health.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from components.branding import show_attribution, show_methodology
from components.data_access import get_engine
from components.mission import (
    build_mission_brief_markdown,
    export_watchlist_json,
    get_mission_context,
    render_mission_context_controls,
    render_watchlist_panel,
    situation_snapshot,
)
try:
    from components.ui import (
    banner,
    empty_state,
    footer_note,
    kpi_row,
    page_header,
    persona_selector,
    status_bar,
    status_strip,
    tile_grid,
    )
except Exception:
    def banner(*_a, **_k):
        pass
    def empty_state(*_a, **_k):
        pass
    def footer_note(*_a, **_k):
        pass
    def kpi_row(*_a, **_k):
        pass
    def page_header(*_a, **_k):
        pass
    def persona_selector(*_a, **_k):
        return "Operator"
    def status_bar(*_a, **_k):
        pass
    def status_strip(*_a, **_k):
        pass
    def tile_grid(*_a, **_k):
        pass

try:
    from ow_theme import apply_theme

    apply_theme()
except Exception:
    # Theme must never block the home cockpit on Streamlit Cloud.
    pass

# ---------------------------------------------------------------------------
# Header + mission
# ---------------------------------------------------------------------------
page_header(
    "OceanWatch Home",
    "Multi-domain maritime cockpit for Kenya EEZ & Western Indian Ocean — "
    "situation, ports, fisheries, risk, and data health in one place.",
    chips=[
        ("Kenya-first", "primary"),
        ("Live warehouse", "info"),
        ("Operator cockpit", "success"),
    ],
)

ctx = render_mission_context_controls(compact=False, key_prefix="home_mc")
persona = persona_selector(
    [
        "Operator",
        "Executive",
        "Port operations",
        "MCS / Fisheries",
        "Research / Science",
        "Watch officer",
    ]
)
lookback = int(ctx.get("lookback_h") or 24)

# ---------------------------------------------------------------------------
# Data load
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _engine():
    return get_engine()


@st.cache_data(ttl=90, show_spinner=False)
def _load_pack(lookback_h: int, persona: str):
    from services.home_cockpit import HomeCockpitService

    return HomeCockpitService(engine=_engine()).build(lookback_h=lookback_h, persona=persona)


@st.cache_data(ttl=90, show_spinner=False)
def _world_pulse():
    try:
        from services.world_class import (
            benchmark_snapshot,
            decision_cards,
            global_pulse,
            narrative_brief,
        )

        eng = _engine()
        pulse = global_pulse(eng)
        cards = decision_cards(eng, pulse)
        brief = narrative_brief(eng, pulse, cards)
        bench = benchmark_snapshot(eng)
        return pulse, cards, brief, bench, None
    except Exception as exc:  # noqa: BLE001
        return None, [], None, pd.DataFrame(), str(exc)


with st.spinner("Fusing multi-domain home picture…"):
    load_err = None
    try:
        pack = _load_pack(lookback, persona)
    except Exception as exc:  # noqa: BLE001
        pack = None
        load_err = str(exc)
    pulse, cards, narrative, bench, world_err = _world_pulse()
    try:
        snap = situation_snapshot(_engine(), ctx)
    except Exception:  # noqa: BLE001
        snap = {}

if load_err or pack is None:
    banner("Home data error", load_err or "Could not build home pack", tone="danger")
    empty_state(
        "Cockpit offline",
        "Check warehouse connectivity and Phase jobs, then refresh.",
        icon="⚠️",
    )
    show_methodology()
    show_attribution()
    footer_note()
    st.stop()

# Sidebar ops
with st.sidebar:
    st.markdown("### Home controls")
    if st.button("Refresh cockpit", use_container_width=True, type="primary"):
        st.cache_data.clear()
        st.rerun()
    st.caption(f"Pack · {pack.generated_at}")
    st.caption(f"Persona · {persona}")
    st.caption(f"Lookback · {lookback}h · region {ctx.get('region', 'KE')}")
    render_watchlist_panel(editable=True, key_prefix="home_wl")

# ---------------------------------------------------------------------------
# Hero posture
# ---------------------------------------------------------------------------
tone_map = {"GREEN": "success", "AMBER": "warning", "RED": "danger", "UNKNOWN": "info"}
posture_tone = tone_map.get(pack.overall, "info")
banner(
    f"{pack.overall} — {pack.overall_label}",
    f"Health {pack.overall_score:.0f}/100 · {pack.kpis.get('vessels', 0)} vessels · "
    f"{pack.kpis.get('alerts', 0)} alerts · port ops {pack.kpis.get('port_level')} · "
    f"data health {pack.kpis.get('data_health_pct')}% · lookback {lookback}h",
    tone=posture_tone,
)

kpi_row(
    [
        {
            "label": "Posture",
            "value": f"{pack.overall_score:.0f}",
            "hint": pack.overall_label,
            "tone": posture_tone,
        },
        {
            "label": "Vessels",
            "value": f"{int(pack.kpis.get('vessels') or 0)}",
            "hint": f"last {lookback}h",
            "tone": "primary",
        },
        {
            "label": "Alerts",
            "value": f"{int(pack.kpis.get('alerts') or 0)}",
            "hint": f"high-risk {int(pack.kpis.get('high_risk') or 0)}",
            "tone": "warning" if (pack.kpis.get("alerts") or 0) >= 5 else "info",
        },
        {
            "label": "Port ops",
            "value": f"{float(pack.kpis.get('port_ops') or 0):.0f}",
            "hint": str(pack.kpis.get("port_level") or "—"),
            "tone": "danger"
            if str(pack.kpis.get("port_level") or "").upper() in ("HIGH", "CRITICAL")
            else "warning"
            if str(pack.kpis.get("port_level") or "").upper() == "MODERATE"
            else "success",
        },
        {
            "label": "Fishing",
            "value": f"{float(pack.kpis.get('fishing_hours') or 0):.0f}h",
            "hint": f"events {int(pack.kpis.get('fishing_events') or 0)}",
            "tone": "info",
        },
        {
            "label": "Data health",
            "value": f"{float(pack.kpis.get('data_health_pct') or 0):.0f}%",
            "hint": f"events {int(pack.kpis.get('events') or 0)}",
            "tone": "success" if (pack.kpis.get("data_health_pct") or 0) >= 70 else "warning",
        },
        {
            "label": "KPA list",
            "value": f"{int(pack.kpis.get('kpa_vessels') or 0)}",
            "hint": f"report {pack.kpis.get('kpa_report_date') or '—'} · ETA48h {int(pack.kpis.get('arrivals_48h') or 0)}",
            "tone": "primary" if (pack.kpis.get("kpa_vessels") or 0) else "warning",
        },
        {
            "label": "Seas",
            "value": (
                f"{float(pack.kpis['wave_m']):.1f} m"
                if pack.kpis.get("wave_m") is not None
                else "—"
            ),
            "hint": f"wind {pack.kpis.get('wind_ms') or '—'} m/s · matches {int(pack.kpis.get('kpa_ais_matches') or 0)}",
            "tone": "warning"
            if pack.kpis.get("wave_m") is not None and float(pack.kpis.get("wave_m") or 0) >= 2.0
            else "info",
        },
    ]
)

# Quick links: live feeds + KPA
with st.container():
    lf1, lf2, lf3, lf4 = st.columns(4)
    with lf1:
        st.page_link("pages/40_Port_Ops_Board.py", label="Port Ops Board — Mombasa →")
        st.page_link("pages/41_Mombasa_Port_Today.py", label="Mombasa Port Today →")
    with lf2:
        st.page_link("pages/39_Live_Feeds_and_KPA.py", label="Live feeds & KPA 14-day list →")
    with lf3:
        st.page_link("pages/8_Port_Intelligence.py", label="Port Intelligence — Mombasa →")
    with lf4:
        st.page_link("pages/35_Ocean_State.py", label="Ocean State →")

# Domain mosaic
st.markdown("### Domain mosaic")
status_emoji = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴", "UNKNOWN": "⚪", "OFF": "⬛"}
dom_cols = st.columns(4)
for i, d in enumerate(pack.domains):
    with dom_cols[i % 4]:
        st.markdown(
            f"**{status_emoji.get(d.status, '⚪')} {d.title}**  \n"
            f"`{d.status}` · **{d.score:.0f}**  \n"
            f"{d.headline}"
        )
        st.caption(d.detail)
        if d.page:
            try:
                st.page_link(
                    d.page,
                    label=f"Open {d.title.split('—')[0].strip()} →",
                    icon=":material/arrow_forward:",
                )
            except Exception:  # noqa: BLE001
                st.caption(d.page)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_sit, tab_attn, tab_port, tab_launch, tab_intel, tab_data = st.tabs(
    [
        "Situation",
        "Attention & actions",
        "Port focus",
        "Launchpad",
        "Intelligence brief",
        "Data health",
    ]
)

# ===== SITUATION =====
with tab_sit:
    left, right = st.columns((1.35, 1))
    with left:
        st.markdown("#### Narrative situation")
        if narrative:
            st.markdown(narrative)
        else:
            st.markdown(
                f"**{pack.overall_label}.** Across the mission window OceanWatch sees "
                f"**{pack.kpis.get('vessels', 0)}** vessels, **{pack.kpis.get('alerts', 0)}** alerts, "
                f"Mombasa port ops **{pack.kpis.get('port_level')}** "
                f"(score {float(pack.kpis.get('port_ops') or 0):.0f}, "
                f"congestion {float(pack.kpis.get('port_cong') or 0):.0f}), "
                f"and data health **{pack.kpis.get('data_health_pct')}%**. "
                f"Ocean signal: _{pack.kpis.get('ocean')}_."
            )
            if pack.port_summary.get("brief"):
                st.markdown(pack.port_summary["brief"])
            if world_err:
                st.caption(f"World-class layer note: {world_err}")

        if cards:
            st.markdown("#### Decision cards")
            for c in cards[:6]:
                title = getattr(c, "title", None) or (c.get("title") if isinstance(c, dict) else "Decision")
                why = getattr(c, "why", None) or (c.get("why") if isinstance(c, dict) else "")
                action = getattr(c, "action", None) or (c.get("action") if isinstance(c, dict) else "")
                sev = getattr(c, "severity", None) or (c.get("severity") if isinstance(c, dict) else "INFO")
                page_hint = getattr(c, "page_hint", None) or (c.get("page_hint") if isinstance(c, dict) else "")
                with st.container(border=True):
                    st.markdown(f"**{sev} · {title}**")
                    if why:
                        st.write(why)
                    if action:
                        st.caption(f"Action: {action}")
                    if page_hint:
                        st.caption(f"Open: {page_hint}")

        if pulse is not None:
            st.markdown("#### Fusion pulse")
            status_strip(
                [
                    ("Overall", getattr(pulse, "overall", pack.overall)),
                    ("Vessels", str(getattr(pulse, "vessels", pack.kpis.get("vessels")))),
                    ("Alerts 24h", str(getattr(pulse, "alerts_24h", pack.kpis.get("alerts")))),
                    (
                        "Port",
                        f"{getattr(pulse, 'port_risk', '—')} ({float(getattr(pulse, 'port_score', 0) or 0):.0f})",
                    ),
                    ("Fishing", str(getattr(pulse, "fishing_hint", pack.kpis.get("fishing_hours")))),
                    (
                        "Fresh",
                        f"{getattr(pulse, 'freshness_ok', 0)}/{getattr(pulse, 'freshness_total', 0)}",
                    ),
                ]
            )

    with right:
        st.markdown("#### Situation timeline")
        if pack.timeline:
            for item in pack.timeline[:12]:
                st.markdown(
                    f"`{item.get('when', '')}` · **{item.get('kind', '')}** — {item.get('text', '')}"
                )
        else:
            st.caption("No timeline items yet.")

        st.markdown("#### Mission snapshot")
        metrics = (snap or {}).get("metrics") or {}
        if metrics:
            # keep it compact
            show = {k: metrics[k] for k in list(metrics)[:16]}
            st.json(show)
        else:
            st.caption("Mission snapshot metrics unavailable.")

        if isinstance(bench, pd.DataFrame) and not bench.empty:
            st.markdown("#### Benchmark strip")
            st.dataframe(bench, width="stretch", hide_index=True)

# ===== ATTENTION =====
with tab_attn:
    c1, c2 = st.columns((1.1, 1))
    with c1:
        st.markdown("#### Attention queue")
        if not pack.attention:
            st.success("Clear — no priority items.")
        else:
            for a in pack.attention:
                sev = str(a.get("severity") or "INFO").upper()
                icon = {"CRITICAL": "🔴", "HIGH": "🟠", "WATCH": "🟡", "INFO": "🟢"}.get(sev, "⚪")
                with st.container(border=True):
                    st.markdown(
                        f"{icon} **{sev}** · {a.get('domain')} — {a.get('title')}  \n"
                        f"{a.get('detail')}"
                    )
                    if a.get("page"):
                        try:
                            st.page_link(a["page"], label="Investigate →")
                        except Exception:  # noqa: BLE001
                            st.caption(a["page"])

    with c2:
        st.markdown("#### Guided next actions")
        st.caption(f"Persona-aware for **{persona}**")
        for a in pack.next_actions:
            with st.container(border=True):
                st.markdown(f"**{a.get('priority')}** · {a.get('title')}  \n_{a.get('why')}_")
                if a.get("page"):
                    try:
                        st.page_link(a["page"], label="Go →")
                    except Exception:  # noqa: BLE001
                        st.caption(a["page"])

    st.markdown("#### Domain status chips")
    status_bar(
        [f"{d.title.split('—')[0].strip()}: {d.status} {d.score:.0f}" for d in pack.domains]
    )

# ===== PORT =====
with tab_port:
    ps = pack.port_summary or {}
    st.markdown("#### Mombasa port focus")
    if ps.get("brief"):
        st.markdown(ps["brief"])
    p1, p2, p3, p4, p5 = st.columns(5)
    p1.metric("Ops risk", f"{float(ps.get('ops_risk') or 0):.0f}", str(ps.get("ops_level") or ""))
    p2.metric("Congestion", f"{float(ps.get('congestion') or 0):.0f}")
    p3.metric("Performance", f"{float(ps.get('performance') or 0):.0f}")
    p4.metric("Arrivals", f"{int(ps.get('arrivals') or 0)}", f"dep {int(ps.get('departures') or 0)}")
    p5.metric("Berth pressure", f"{float(ps.get('pressure') or 0):.0f}")

    alerts = ps.get("alerts") or []
    if alerts:
        st.markdown("##### Port watchlist")
        st.dataframe(pd.DataFrame(alerts), width="stretch", hide_index=True)

    l, r = st.columns(2)
    with l:
        st.page_link("pages/8_Port_Intelligence.py", label="Port Intelligence — full cockpit →")
        st.page_link("pages/29_Port_Intelligence_Advanced.py", label="Advanced diagnostics →")
    with r:
        st.page_link("pages/12_Port_Risk.py", label="Port Risk (ML) →")
        st.page_link("pages/4_Vessel_Tracking.py", label="Vessel tracks / port calls →")

    st.caption("Port figures are OceanWatch decision-support estimates — not official KPA statistics.")

# ===== LAUNCHPAD =====
with tab_launch:
    st.markdown(f"#### Persona launchpad · _{persona}_")
    st.caption("Grouped deep-links across the OceanWatch canvas. Sidebar remains the full nav.")

    groups: dict[str, list] = {}
    for item in pack.launchpad:
        groups.setdefault(item["group"], []).append(item)

    for group, items in groups.items():
        st.markdown(f"##### {group}")
        n = min(4, len(items)) or 1
        cols = st.columns(n)
        for i, it in enumerate(items):
            with cols[i % n]:
                with st.container(border=True):
                    st.markdown(f"**{it['title']}**")
                    st.caption(it.get("blurb") or "")
                    try:
                        st.page_link(it["page"], label="Open →")
                    except Exception:  # noqa: BLE001
                        st.caption(it["page"])

    st.markdown("##### Favourites strip")
    tile_grid(
        [
            {"title": "EEZ Today", "detail": "Daily national watch", "icon": "🌍"},
            {"title": "Command Center", "detail": "Fused multi-domain ops", "icon": "🎛️"},
            {"title": "AIS Live", "detail": "Near real-time positions", "icon": "📡"},
            {"title": "Port Mombasa", "detail": "Congestion · berth · risk", "icon": "⚓"},
            {"title": "Alerts", "detail": "Operational alert queue", "icon": "⚠️"},
            {"title": "Fisheries", "detail": "MCS / effort picture", "icon": "🎣"},
        ]
    )
    fav_cols = st.columns(6)
    fav_pages = [
        "pages/0_Kenya_EEZ_Today.py",
        "pages/3_Command_Center.py",
        "pages/11_AIS_Live.py",
        "pages/8_Port_Intelligence.py",
        "pages/7_Operational_Alerts.py",
        "pages/30_Fisheries_Intelligence.py",
    ]
    for col, page in zip(fav_cols, fav_pages):
        with col:
            try:
                st.page_link(page, label="Open →")
            except Exception:  # noqa: BLE001
                pass

# ===== INTEL =====
with tab_intel:
    st.markdown("#### Intelligence brief & copilot")
    svc_line = st.text_input(
        "Ask the home copilot",
        placeholder="e.g. What should I do first? Port status? High risk vessels?",
        key="home_copilot_q",
    )
    if svc_line.strip():
        try:
            from services.world_class import intelligence_copilot

            ans = intelligence_copilot(_engine(), svc_line.strip(), pulse=pulse, cards=cards or None)
            if isinstance(ans, dict):
                st.markdown(ans.get("answer") or ans.get("text") or str(ans))
                pages = ans.get("suggested_pages") or []
                if pages:
                    st.caption("Suggested: " + " · ".join(str(p) for p in pages[:6]))
            else:
                st.write(ans)
        except Exception as exc:  # noqa: BLE001
            st.info(f"Copilot unavailable ({exc}). Use the narrative brief below.")

    from services.home_cockpit import HomeCockpitService

    brief_md = HomeCockpitService(engine=_engine()).markdown_brief(
        pack, {**ctx, "persona": persona}
    )
    try:
        mission_md = build_mission_brief_markdown(snap, ctx)
        if mission_md:
            brief_md = brief_md + "\n\n---\n\n## Mission export\n\n" + mission_md
    except Exception:  # noqa: BLE001
        pass

    with st.expander("Full markdown brief", expanded=True):
        st.markdown(brief_md)

    b1, b2 = st.columns(2)
    with b1:
        st.download_button(
            "Download home brief (Markdown)",
            data=brief_md.encode("utf-8"),
            file_name=f"oceanwatch_home_brief_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with b2:
        st.download_button(
            "Download watchlist (JSON)",
            data=export_watchlist_json().encode("utf-8"),
            file_name="oceanwatch_watchlist.json",
            mime="application/json",
            use_container_width=True,
        )

    st.markdown("#### Recent multi-domain events")
    if pack.recent_events is None or pack.recent_events.empty:
        st.caption("No recent event rows in warehouse extracts.")
    else:
        st.dataframe(pack.recent_events.head(30), width="stretch", hide_index=True)

# ===== DATA =====
with tab_data:
    st.markdown("#### Warehouse freshness mosaic")
    fresh = pack.freshness
    if fresh is None or fresh.empty:
        st.caption("No freshness rows.")
    else:
        def _badge(s: str) -> str:
            return {
                "OK": "✅",
                "AGING": "🟡",
                "STALE": "🟠",
                "EMPTY": "⚪",
                "MISSING": "❌",
            }.get(str(s), "·")

        view = fresh.copy()
        view.insert(0, " ", view["status"].map(_badge))
        st.dataframe(view, width="stretch", hide_index=True)

        ok = int((fresh["status"] == "OK").sum())
        st.metric("Healthy layers", f"{ok}/{len(fresh)}")

        c1, c2, c3 = st.columns(3)
        with c1:
            st.page_link("pages/32_Data_Catalog.py", label="Data Catalog →")
        with c2:
            st.page_link("pages/31_Platform_Operations.py", label="Platform Ops →")
        with c3:
            st.page_link("pages/25_Quality_and_Provenance.py", label="Quality & Provenance →")

    if pack.errors:
        with st.expander("Home pack query warnings"):
            for e in pack.errors[:12]:
                st.code(e)

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption(
    f"OceanWatch Home · generated {pack.generated_at} · persona {persona} · "
    f"posture {pack.overall} ({pack.overall_score}) · "
    "decision-support only, not official authority figures."
)
show_methodology()
show_attribution()
footer_note()
