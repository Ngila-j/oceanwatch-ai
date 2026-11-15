"""
Watch Floor — full-width multi-domain ops wall.

Designed for NOC / SOCs: pulse, decision cards, live KPIs, port, AIS, brief.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

_APP = Path(__file__).resolve().parents[1]
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from components.i18n import get_lang, render_lang_toggle, t  # noqa: E402
from components.pagekit import boot, close_page  # noqa: E402
from components.ui import banner, kpi_row  # noqa: E402
from components.data_access import get_engine  # noqa: E402

try:
    from services.world_class import (
        decision_cards,
        global_pulse,
        narrative_brief,
        benchmark_snapshot,
    )
except ImportError:  # pragma: no cover
    from streamlit_app.services.world_class import (  # type: ignore
        decision_cards,
        global_pulse,
        narrative_brief,
        benchmark_snapshot,
    )


boot(
    t("watch_floor"),
    "Full-screen multi-domain wall · pulse · decisions · port · AIS · auto-brief",
    chips=[
        (t("world_class"), "primary"),
        ("NOC", "info"),
        ("Kenya EEZ", "info"),
    ],
)

# Watch-floor chrome
st.markdown(
    """
<style>
  section.main .block-container { padding-top: 1rem; max-width: 1400px; }
  .ow-pulse-wall {
    border-radius: 16px; padding: 1.1rem 1.4rem; margin-bottom: 1rem;
    border: 1px solid rgba(11,61,92,0.15);
    background: linear-gradient(135deg, #0B3D5C 0%, #0E7490 55%, #0369A1 100%);
    color: #F8FAFC; box-shadow: 0 12px 40px rgba(11,61,92,0.25);
  }
  .ow-pulse-wall h2 { color: #fff !important; margin: 0 0 .35rem 0; font-size: 1.55rem; }
  .ow-pulse-wall .meta { opacity: 0.9; font-size: 0.92rem; }
  .ow-card-crit { border-left: 4px solid #DC2626; padding: .6rem .8rem; background: #FEF2F2; border-radius: 8px; margin-bottom: .5rem; }
  .ow-card-high { border-left: 4px solid #EA580C; padding: .6rem .8rem; background: #FFF7ED; border-radius: 8px; margin-bottom: .5rem; }
  .ow-card-watch { border-left: 4px solid #CA8A04; padding: .6rem .8rem; background: #FEFCE8; border-radius: 8px; margin-bottom: .5rem; }
  .ow-card-info { border-left: 4px solid #0284C7; padding: .6rem .8rem; background: #F0F9FF; border-radius: 8px; margin-bottom: .5rem; }
</style>
""",
    unsafe_allow_html=True,
)

c_lang, c_refresh, _ = st.columns([1, 1, 4])
with c_lang:
    render_lang_toggle(key="wf_lang")
with c_refresh:
    auto = st.toggle("Auto-refresh 60s", value=False, key="wf_auto")
    if auto:
        try:
            from streamlit_autorefresh import st_autorefresh

            st_autorefresh(interval=60_000, key="wf_ar")
        except Exception:  # noqa: BLE001
            st.caption("Install streamlit-autorefresh for live wall mode")

engine = get_engine()
with st.spinner("Fusing multi-domain picture…"):
    pulse = global_pulse(engine)
    cards = decision_cards(engine, pulse)
    bench = benchmark_snapshot(engine)
    brief = narrative_brief(engine, pulse, cards)

tone_map = {"GREEN": "#4ADE80", "AMBER": "#FBBF24", "RED": "#F87171"}
dot = tone_map.get(pulse.overall, "#94A3B8")

st.markdown(
    f"""
<div class="ow-pulse-wall" role="status" aria-live="polite">
  <h2><span style="color:{dot}">●</span> {t('pulse')}: {pulse.overall} · {pulse.score:.0f}/100</h2>
  <div class="meta">{pulse.label} · {t('vessels')} {pulse.vessels} · {t('alerts')} {pulse.alerts_24h}
  · {t('port')} {pulse.port_score:.0f} ({pulse.port_risk}) · {pulse.ocean_hint}
  · {t('freshness')} {pulse.freshness_ok}/{pulse.freshness_total}
  · lang={get_lang().upper()}</div>
</div>
""",
    unsafe_allow_html=True,
)

kpi_row(
    [
        {
            "label": t("vessels"),
            "value": f"{pulse.vessels:,}",
            "hint": "24h AIS",
            "tone": "primary" if pulse.vessels else "danger",
        },
        {
            "label": t("alerts"),
            "value": f"{pulse.alerts_24h:,}",
            "hint": "24h",
            "tone": "danger" if pulse.alerts_24h >= 8 else "info",
        },
        {
            "label": t("port"),
            "value": f"{pulse.port_score:.0f}",
            "hint": pulse.port_risk,
            "tone": "danger" if pulse.port_score >= 70 else "warning" if pulse.port_score >= 45 else "success",
        },
        {
            "label": t("freshness"),
            "value": f"{pulse.freshness_ok}/{pulse.freshness_total}",
            "hint": "domains recent",
            "tone": "success" if pulse.freshness_ok >= max(2, pulse.freshness_total // 2) else "warning",
        },
        {
            "label": "Ocean",
            "value": pulse.ocean_hint if pulse.ocean_hint != "—" else "—",
            "hint": "SST / index",
            "tone": "info",
        },
    ]
)

left, right = st.columns([1.15, 1])

with left:
    st.markdown(f"### {t('decisions')}")
    css = {
        "CRITICAL": "ow-card-crit",
        "HIGH": "ow-card-high",
        "WATCH": "ow-card-watch",
        "INFO": "ow-card-info",
    }
    for c in cards[:8]:
        cls = css.get(c.urgency, "ow-card-info")
        st.markdown(
            f'<div class="{cls}"><b>[{c.urgency}] {c.title}</b> · <i>{c.domain}</i><br>'
            f"{c.why}<br><b>→</b> {c.action}"
            f"{(' · <code>' + c.page_hint + '</code>') if c.page_hint else ''}"
            f"</div>",
            unsafe_allow_html=True,
        )

with right:
    st.markdown(f"### {t('brief')}")
    st.download_button(
        t("export_brief"),
        data=brief.encode("utf-8"),
        file_name="oceanwatch_situation_brief.md",
        mime="text/markdown",
        type="primary",
        width="stretch",
    )
    st.code(brief, language="markdown")

st.markdown("### Benchmark strip")
if bench is not None and not bench.empty:
    st.dataframe(bench, width="stretch", hide_index=True)
else:
    banner("No benchmark", "Pulse engine returned empty.", tone="warning")

# Live tables strip
st.markdown("### Live feeds")
t1, t2, t3 = st.tabs(["Port ops risk", "High-risk vessels", "Recent activity"])
with t1:
    try:
        df = pd.read_sql(
            "SELECT * FROM fact_port_ops_risk ORDER BY as_of DESC LIMIT 5",
            engine,
        )
        st.dataframe(df, width="stretch", hide_index=True)
    except Exception as exc:  # noqa: BLE001
        st.caption(str(exc))
with t2:
    try:
        df = pd.read_sql(
            """
            SELECT mmsi, vessel_name, vessel_type, flag,
                   COALESCE(risk_score, behaviour_score) AS score
            FROM fact_vessel_profiles
            WHERE COALESCE(risk_score, behaviour_score, 0) >= 55
            ORDER BY score DESC NULLS LAST
            LIMIT 40
            """,
            engine,
        )
        st.dataframe(df, width="stretch", hide_index=True)
    except Exception:  # noqa: BLE001
        st.info("No vessel profiles yet — run vessel tracking ingest.")
with t3:
    try:
        df = pd.read_sql(
            """
            SELECT event_time, event_type, mmsi, vessel_name, vessel_type
            FROM fact_port_activity
            ORDER BY event_time DESC NULLS LAST
            LIMIT 40
            """,
            engine,
        )
        st.dataframe(df, width="stretch", hide_index=True)
    except Exception:  # noqa: BLE001
        st.info("No port activity rows.")

st.caption(
    "Watch Floor is a decision-support wall for OceanWatch operators — "
    "not an official Kenya Ports Authority or navy COP."
)
close_page()
