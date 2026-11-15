"""
Lightweight EN / Kiswahili strings for OceanWatch operator UI.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

STRINGS: dict[str, dict[str, str]] = {
    "app_tagline": {
        "en": "Maritime intelligence for Kenya’s EEZ & the Western Indian Ocean",
        "sw": "Ujasusi wa bahari kwa EEZ ya Kenya na Bahari ya Hindi Magharibi",
    },
    "mission": {"en": "Mission", "sw": "Misheni"},
    "situation": {"en": "Situation", "sw": "Hali"},
    "pulse": {"en": "Global pulse", "sw": "Mpigo wa hali"},
    "stable": {"en": "Situation stable", "sw": "Hali thabiti"},
    "elevated": {"en": "Elevated attention", "sw": "Angalizo lililoinuka"},
    "priority": {"en": "Priority response", "sw": "Majibu ya kipaumbele"},
    "decisions": {"en": "Priority decisions", "sw": "Maamuzi ya kipaumbele"},
    "copilot": {"en": "Intelligence Copilot", "sw": "Copilot wa Ujasusi"},
    "watch_floor": {"en": "Watch Floor", "sw": "Sakafu ya Uangalizi"},
    "brief": {"en": "Situation brief", "sw": "Muhtasari wa hali"},
    "vessels": {"en": "Vessels", "sw": "Meli"},
    "alerts": {"en": "Alerts", "sw": "Tahadhari"},
    "port": {"en": "Port risk", "sw": "Hatari ya bandari"},
    "freshness": {"en": "Data freshness", "sw": "Upya wa data"},
    "ask": {"en": "Ask OceanWatch", "sw": "Uliza OceanWatch"},
    "export_brief": {"en": "Export brief", "sw": "Pakua muhtasari"},
    "language": {"en": "Language", "sw": "Lugha"},
    "find_domain": {"en": "Find a domain", "sw": "Tafuta kikoa"},
    "search_ph": {
        "en": "AIS, bloom, port, risk…",
        "sw": "AIS, maua, bandari, hatari…",
    },
    "world_class": {
        "en": "World-class ops",
        "sw": "Operesheni za kiwango cha dunia",
    },
}


def get_lang() -> str:
    lang = st.session_state.get("ow_lang", "en")
    return lang if lang in ("en", "sw") else "en"


def set_lang(lang: str) -> None:
    st.session_state["ow_lang"] = "sw" if lang == "sw" else "en"


def t(key: str, **kwargs: Any) -> str:
    lang = get_lang()
    block = STRINGS.get(key) or {}
    text = block.get(lang) or block.get("en") or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:  # noqa: BLE001
            return text
    return text


def render_lang_toggle(*, key: str = "ow_lang_toggle") -> str:
    labels = {"en": "English", "sw": "Kiswahili"}
    cur = get_lang()
    choice = st.radio(
        t("language"),
        options=["en", "sw"],
        format_func=lambda x: labels[x],
        horizontal=True,
        index=0 if cur == "en" else 1,
        key=key,
        label_visibility="collapsed",
    )
    set_lang(choice)
    return choice
