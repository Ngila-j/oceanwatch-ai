"""
Lightweight page bootstrap for OceanWatch multipage scripts.

Call `boot(title, description, ...)` near the top of each page (after imports).
Safe if Streamlit already configured page via st.Page shell.
"""

from __future__ import annotations

from typing import Optional, Sequence

import streamlit as st

from components.branding import show_attribution, show_methodology
from components.ui import ensure_theme, footer_note, page_header
from ow_theme import init_a11y_defaults


def boot(
    title: str,
    description: str = "",
    *,
    kicker: str = "OceanWatch AI",
    chips: Optional[Sequence[tuple[str, str]]] = None,
    page_title: Optional[str] = None,
    icon: str = "🌊",
) -> None:
    """Theme + accessible page header. Ignores set_page_config errors under st.Page."""
    init_a11y_defaults()
    try:
        st.set_page_config(
            page_title=page_title or f"{title} · OceanWatch",
            page_icon=icon,
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except Exception:
        # Already configured by OceanWatch shell
        pass
    ensure_theme()
    page_header(title, description, kicker=kicker, chips=list(chips or ()))


def close_page(*, methodology: bool = True, attribution: bool = True) -> None:
    if methodology:
        show_methodology()
    if attribution:
        show_attribution()
    footer_note()
