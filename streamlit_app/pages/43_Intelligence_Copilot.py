"""
Intelligence Copilot — ask natural questions over the warehouse.

Deterministic, evidence-backed answers (no hallucinated LLM calls required).
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

_APP = Path(__file__).resolve().parents[1]
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

from components.data_access import get_engine  # noqa: E402
from components.i18n import render_lang_toggle, t  # noqa: E402
from components.pagekit import boot, close_page  # noqa: E402
from components.ui import banner, kpi_row  # noqa: E402

try:
    from services.world_class import (
        _COPILOT_HINTS,
        copilot_answer,
        global_pulse,
        narrative_brief,
    )
except ImportError:  # pragma: no cover
    from streamlit_app.services.world_class import (  # type: ignore
        _COPILOT_HINTS,
        copilot_answer,
        global_pulse,
        narrative_brief,
    )


boot(
    t("copilot"),
    "Natural-language questions · multi-domain evidence · Kenya EEZ first",
    chips=[(t("world_class"), "primary"), ("Ask", "info"), ("No API key required", "success")],
)

render_lang_toggle(key="cp_lang")

engine = get_engine()
pulse = global_pulse(engine)

kpi_row(
    [
        {
            "label": t("pulse"),
            "value": f"{pulse.overall} {pulse.score:.0f}",
            "hint": pulse.label,
            "tone": "success"
            if pulse.overall == "GREEN"
            else "warning"
            if pulse.overall == "AMBER"
            else "danger",
        },
        {"label": t("vessels"), "value": f"{pulse.vessels}", "hint": "24h", "tone": "primary"},
        {
            "label": t("port"),
            "value": f"{pulse.port_score:.0f}",
            "hint": pulse.port_risk,
            "tone": "info",
        },
        {
            "label": t("alerts"),
            "value": f"{pulse.alerts_24h}",
            "hint": "24h",
            "tone": "warning" if pulse.alerts_24h else "success",
        },
    ]
)

st.markdown(f"### {t('ask')}")
st.caption(
    "Examples work offline against your warehouse — port risk, AIS, alerts, SST, freshness, briefs."
)

if "ow_copilot_chat" not in st.session_state:
    st.session_state["ow_copilot_chat"] = []

hints = st.multiselect(
    "Quick prompts",
    options=list(_COPILOT_HINTS),
    default=[],
    max_selections=1,
    key="cp_hints",
)
q_default = hints[0] if hints else ""
question = st.text_input(
    t("ask"),
    value=q_default,
    placeholder="e.g. How is Mombasa port right now?",
    key="cp_q",
    label_visibility="collapsed",
)

c1, c2, c3 = st.columns([1, 1, 2])
with c1:
    go = st.button("Ask", type="primary", width="stretch")
with c2:
    brief_btn = st.button(t("brief"), width="stretch")
with c3:
    clear = st.button("Clear chat", width="stretch")

if clear:
    st.session_state["ow_copilot_chat"] = []
    st.rerun()

if brief_btn:
    question = "Write me a situation brief"
    go = True

if go and str(question).strip():
    with st.spinner("Querying warehouse + fusion engine…"):
        ans = copilot_answer(engine, str(question).strip())
    st.session_state["ow_copilot_chat"].append(ans)
    st.session_state["ow_copilot_chat"] = st.session_state["ow_copilot_chat"][-12:]

for turn in reversed(st.session_state["ow_copilot_chat"]):
    with st.chat_message("user"):
        st.markdown(turn.get("question") or "")
    with st.chat_message("assistant"):
        st.markdown(turn.get("answer") or "_No answer_")
        pages = turn.get("suggested_pages") or []
        if pages:
            st.caption("Suggested pages: " + " · ".join(pages))
        cards = turn.get("cards") or []
        if cards:
            with st.expander("Related decision cards"):
                for c in cards:
                    st.markdown(f"**[{c.urgency}] {c.title}** — {c.action}")
        ev = turn.get("evidence") or {}
        if ev:
            with st.expander("Evidence tables"):
                for k, v in ev.items():
                    st.markdown(f"**{k}**")
                    if isinstance(v, list) and v:
                        st.dataframe(v, width="stretch", hide_index=True)

if not st.session_state["ow_copilot_chat"]:
    banner(
        "Ready",
        "Try “How is Mombasa port right now?”, “Any high-risk vessels?”, or “What should I do first?”",
        tone="info",
    )

st.divider()
st.markdown("#### Full brief (one click)")
md = narrative_brief(engine, pulse)
st.download_button(
    t("export_brief") + " (.md)",
    data=md.encode("utf-8"),
    file_name="oceanwatch_brief.md",
    mime="text/markdown",
)
with st.expander("Preview brief"):
    st.markdown(md)

st.caption(
    "Copilot answers are rule-based over live SQL evidence. "
    "Optional LLM enrichment can be layered later without changing this contract."
)
close_page()
