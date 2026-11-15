"""Executive Summary — multi-domain command brief."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from components.pagekit import boot, close_page
from components.ui import banner, empty_state, kpi_row
from services.home_cockpit import HomeCockpitService
from services.port_ops_board import PortOpsBoardService

boot(
    "Executive Summary",
    "Cross-domain posture · port ops fusion · attention queue · decision-support brief.",
    chips=[
        ("Command brief", "primary"),
        ("Port ops", "info"),
        ("Decision-support", "success"),
    ],
)

with st.sidebar:
    lookback = st.slider("Lookback (hours)", 6, 168, 48, 6)
    persona = st.selectbox(
        "Persona lens",
        ["Operator", "Executive", "Port Authority", "Fisheries", "Analyst"],
        index=1,
    )


@st.cache_data(ttl=120, show_spinner=False)
def _home(lb: int, persona: str):
    return HomeCockpitService().build(lookback_h=lb, persona=persona)


@st.cache_data(ttl=90, show_spinner=False)
def _ops():
    return PortOpsBoardService().load_pack()


with st.spinner("Assembling executive picture…"):
    err = None
    pack = None
    ops = None
    try:
        pack = _home(int(lookback), persona)
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
    try:
        ops = _ops()
    except Exception as exc:  # noqa: BLE001
        if err:
            err = f"{err} | ops: {exc}"
        else:
            err = f"ops: {exc}"

if pack is None and ops is None:
    banner("Unable to load summary", err or "No data services", tone="danger")
    close_page()
    st.stop()

if err:
    banner("Partial load", err, tone="warning")

# Posture
if pack is not None:
    tone = {"GREEN": "success", "AMBER": "warning", "RED": "danger"}.get(pack.overall, "info")
    banner(
        f"Overall posture · {pack.overall} · score {pack.overall_score:.0f}",
        pack.overall_label,
        tone=tone,
    )
    k = pack.kpis
    kpi_row(
        [
            {
                "label": "Posture",
                "value": pack.overall,
                "hint": f"{pack.overall_score:.0f}",
                "tone": tone,
            },
            {
                "label": "Vessels",
                "value": str(int(k.get("vessels") or 0)),
                "hint": f"{lookback}h AIS",
                "tone": "primary",
            },
            {
                "label": "Alerts",
                "value": str(int(k.get("alerts") or 0)),
                "hint": f"high-risk {int(k.get('high_risk') or 0)}",
                "tone": "warning" if (k.get("alerts") or 0) else "info",
            },
            {
                "label": "KPA vessels",
                "value": str(int(k.get("kpa_vessels") or 0)),
                "hint": str(k.get("kpa_report_date") or "—"),
                "tone": "primary" if k.get("kpa_vessels") else "warning",
            },
            {
                "label": "ETA ≤48h",
                "value": str(int(k.get("arrivals_48h") or 0)),
                "hint": f"matches {int(k.get('kpa_ais_matches') or 0)}",
                "tone": "warning" if (k.get("arrivals_48h") or 0) >= 8 else "info",
            },
            {
                "label": "Seas",
                "value": f"{float(k['wave_m']):.1f} m" if k.get("wave_m") is not None else "—",
                "hint": f"data health {float(k.get('data_health_pct') or 0):.0f}%",
                "tone": "info",
            },
        ]
    )

tab_brief, tab_attn, tab_port, tab_dom = st.tabs(
    ["Brief", "Attention", "Port ops", "Domains"]
)

with tab_brief:
    st.markdown("#### Intelligence brief")
    if pack is not None:
        try:
            st.markdown(HomeCockpitService().markdown_brief(pack))
        except Exception:
            ps = pack.port_summary or {}
            st.markdown(ps.get("brief") or "_No narrative brief available._")
            if pack.fishing_summary:
                st.caption(f"Fishing: {pack.fishing_summary}")
    if ops is not None:
        st.markdown("##### Port Ops Board brief")
        st.markdown(ops.brief)

with tab_attn:
    st.markdown("#### Attention queue")
    if pack is None or not pack.attention:
        empty_state("Clear queue", "No elevated attention items in this window.", icon="✅")
    else:
        for a in pack.attention:
            sev = str(a.get("severity") or "INFO")
            t = {"CRITICAL": "danger", "HIGH": "danger", "WATCH": "warning"}.get(sev, "info")
            banner(f"{sev} · {a.get('domain')}: {a.get('title')}", a.get("detail") or "", tone=t)
            if a.get("page"):
                try:
                    st.page_link(a["page"], label="Open →")
                except Exception:
                    pass

with tab_port:
    st.markdown("#### Mombasa port ops fusion")
    st.page_link("pages/40_Port_Ops_Board.py", label="Open full Port Ops Board →")
    if ops is None:
        empty_state("No ops pack", "Load KPA list and free marine feeds first.", icon="⚓")
    else:
        kpi_row(
            [
                {
                    "label": "KPA",
                    "value": str(ops.kpis.get("kpa_vessels") or 0),
                    "hint": str(ops.kpis.get("kpa_report_date") or "—"),
                    "tone": "primary",
                },
                {
                    "label": "AIS near",
                    "value": str(ops.kpis.get("ais_near") or 0),
                    "hint": "40 nm box",
                    "tone": "info",
                },
                {
                    "label": "Matches",
                    "value": str(ops.kpis.get("matches") or 0),
                    "hint": f"{ops.kpis.get('match_rate_pct') or 0}%",
                    "tone": "success",
                },
                {
                    "label": "Wave",
                    "value": f"{float(ops.kpis['wave_m']):.1f} m"
                    if ops.kpis.get("wave_m") is not None
                    else "—",
                    "hint": "Open-Meteo",
                    "tone": "info",
                },
            ]
        )
        for a in (ops.alerts or [])[:4]:
            banner(f"{a.get('severity')}: {a.get('title')}", a.get("detail") or "", tone="warning")
        if not ops.arrival_board.empty:
            st.markdown("##### Arrival board (top 20)")
            st.dataframe(ops.arrival_board.head(20), width="stretch", hide_index=True)

with tab_dom:
    st.markdown("#### Domain mosaic")
    if pack is None or not pack.domains:
        st.caption("No domain cards.")
    else:
        cols = st.columns(3)
        for i, d in enumerate(pack.domains):
            with cols[i % 3]:
                st.markdown(
                    f"**{d.title}** · `{d.status}` · **{d.score:.0f}**  \n"
                    f"{d.headline}  \n"
                    f"_{d.detail}_"
                )
                if d.page:
                    try:
                        st.page_link(d.page, label="Open →")
                    except Exception:
                        pass

st.markdown("---")
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.page_link("pages/40_Port_Ops_Board.py", label="Port Ops Board →")
with c2:
    st.page_link("pages/39_Live_Feeds_and_KPA.py", label="Live Feeds & KPA →")
with c3:
    st.page_link("pages/3_Command_Center.py", label="Command Center →")
with c4:
    st.page_link("pages/8_Port_Intelligence.py", label="Port Intelligence →")

close_page()
