"""
Reusable OceanWatch UI primitives — headers, KPIs, banners, empty states.
All helpers emit semantic HTML with accessible labels where practical.
"""

from __future__ import annotations

from datetime import datetime, timezone
from html import escape
from typing import Iterable, Mapping, Optional, Sequence

import streamlit as st

from ow_theme import apply_theme, init_a11y_defaults


def ensure_theme() -> None:
    """Idempotent theme + a11y bootstrap for multipage entry points."""
    init_a11y_defaults()
    apply_theme()


def page_header(
    title: str,
    description: str = "",
    *,
    kicker: str = "OceanWatch AI",
    chips: Optional[Sequence[tuple[str, str]]] = None,
) -> None:
    """
    Standard page masthead.
    chips: list of (label, tone) where tone in
           neutral|success|warning|danger|info|primary
    """
    ensure_theme()
    chip_html = ""
    if chips:
        parts = []
        for label, tone in chips:
            tone = tone or "neutral"
            parts.append(
                f'<span class="ow-chip ow-chip-{escape(tone)}" '
                f'role="status">{escape(label)}</span>'
            )
        chip_html = f'<div class="ow-page-meta" aria-label="Status">{"".join(parts)}</div>'

    desc = (
        f'<p class="ow-page-desc">{escape(description)}</p>' if description else ""
    )
    st.markdown(
        f"""
        <header class="ow-page-header" role="banner">
          <div>
            <p class="ow-page-kicker">{escape(kicker)}</p>
            <h1 class="ow-page-title">{escape(title)}</h1>
            {desc}
          </div>
          {chip_html}
        </header>
        """,
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str = "") -> None:
    sub = f"<p>{escape(subtitle)}</p>" if subtitle else ""
    st.markdown(
        f"""
        <div class="ow-section">
          <h2>{escape(title)}</h2>
          {sub}
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(items: Sequence[Mapping[str, str]]) -> None:
    """
    items: dicts with keys label, value, optional hint, tone
    """
    cells = []
    for item in items:
        tone = escape(str(item.get("tone") or "primary"))
        label = escape(str(item.get("label") or ""))
        value = escape(str(item.get("value") or "—"))
        hint = escape(str(item.get("hint") or ""))
        hint_html = f'<p class="ow-kpi-hint">{hint}</p>' if hint else ""
        cells.append(
            f"""
            <div class="ow-kpi" data-tone="{tone}" role="group"
                 aria-label="{label}: {value}">
              <p class="ow-kpi-label">{label}</p>
              <p class="ow-kpi-value">{value}</p>
              {hint_html}
            </div>
            """
        )
    st.markdown(
        f'<div class="ow-kpi-grid" role="list">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )


def banner(
    title: str,
    text: str = "",
    *,
    tone: str = "info",
    icon: str = "ℹ️",
) -> None:
    tone = tone if tone in {"info", "success", "warning", "danger"} else "info"
    body = f'<p class="ow-banner-text">{escape(text)}</p>' if text else ""
    st.markdown(
        f"""
        <div class="ow-banner ow-banner-{tone}" role="status" aria-live="polite">
          <div class="ow-banner-icon" aria-hidden="true">{icon}</div>
          <div class="ow-banner-body">
            <p class="ow-banner-title">{escape(title)}</p>
            {body}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def empty_state(title: str, detail: str = "", *, icon: str = "📭") -> None:
    detail_html = f"<p>{escape(detail)}</p>" if detail else ""
    st.markdown(
        f"""
        <div class="ow-empty" role="status">
          <div aria-hidden="true" style="font-size:1.6rem;margin-bottom:0.35rem">{icon}</div>
          <h3>{escape(title)}</h3>
          {detail_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_bar(parts: Iterable[str]) -> None:
    bits = " · ".join(escape(p) for p in parts if p)
    if not bits:
        return
    st.markdown(
        f'<div class="ow-statusbar" role="status" aria-live="polite">{bits}</div>',
        unsafe_allow_html=True,
    )


def chip(label: str, tone: str = "neutral") -> str:
    return (
        f'<span class="ow-chip ow-chip-{escape(tone)}" role="status">'
        f"{escape(label)}</span>"
    )


def footer_note(
    *,
    product: str = "OceanWatch AI",
    extra: str = "Decision-support only — not an official authority product.",
) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    st.markdown(
        f"""
        <footer class="ow-footer" role="contentinfo">
          <span><strong>{escape(product)}</strong> · Kenya EEZ / WIO monitoring</span>
          <span>{escape(extra)}</span>
          <span>Rendered {now}</span>
        </footer>
        """,
        unsafe_allow_html=True,
    )


def tile_grid(tiles: Sequence[Mapping[str, str]]) -> None:
    """
    tiles: title, detail, optional icon, optional href (informational only in Streamlit)
    """
    cells = []
    for t in tiles:
        icon = escape(str(t.get("icon") or "▸"))
        title = escape(str(t.get("title") or ""))
        detail = escape(str(t.get("detail") or ""))
        cells.append(
            f"""
            <div class="ow-tile" role="listitem" tabindex="0"
                 aria-label="{title}. {detail}">
              <div class="ow-tile-icon" aria-hidden="true">{icon}</div>
              <strong>{title}</strong>
              <span>{detail}</span>
            </div>
            """
        )
    st.markdown(
        f'<div class="ow-tile-grid" role="list">{"".join(cells)}</div>',
        unsafe_allow_html=True,
    )


def sidebar_brand(
    title: str = "OceanWatch AI",
    subtitle: str = "Kenya EEZ · Western Indian Ocean",
    mark: str = "OW",
) -> None:
    st.markdown(
        f"""
        <div class="ow-brand" role="banner" aria-label="{escape(title)}">
          <div class="ow-brand-mark" aria-hidden="true">{escape(mark)}</div>
          <div>
            <p class="ow-brand-title">{escape(title)}</p>
            <p class="ow-brand-sub">{escape(subtitle)}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def a11y_sidebar_controls() -> None:
    """Accessibility preferences in the sidebar (persisted in session_state)."""
    init_a11y_defaults()
    st.markdown(
        """
        <div class="ow-a11y-panel" role="region" aria-label="Accessibility settings">
          <h3>Accessibility</h3>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2)
    with c1:
        st.checkbox(
            "Large text",
            key="a11y_large_text",
            help="Increase base font size and spacing for readability.",
        )
        st.checkbox(
            "High contrast",
            key="a11y_high_contrast",
            help="Stronger borders and text contrast (WCAG-oriented).",
        )
        st.checkbox(
            "Underline links",
            key="a11y_underline_links",
            help="Always underline links so color is not the only cue.",
        )
    with c2:
        st.checkbox(
            "Dark mode",
            key="a11y_dark_mode",
            help="Reduce brightness for low-light environments.",
        )
        st.checkbox(
            "Reduce motion",
            key="a11y_reduced_motion",
            help="Disable non-essential animations and transitions.",
        )
        st.checkbox(
            "Low bandwidth",
            key="low_bandwidth",
            help="Prefer lighter tables over heavy charts when pages support it.",
        )
    st.session_state["_ow_bw_widget"] = True
    st.caption(
        "Tip: use **Tab** / **Shift+Tab** to move, **Enter** to activate. "
        "Skip link appears on first Tab."
    )


def persona_selector(options: Optional[Sequence[str]] = None) -> str:
    options = list(options or ("Analyst", "Operations", "Executive", "Researcher", "Partner"))
    if "persona" not in st.session_state:
        st.session_state.persona = options[0]
    choice = st.selectbox(
        "Workspace persona",
        options,
        key="persona",
        help="Soft-filters emphasis on Home and briefings. Does not hide pages.",
    )
    st.markdown(
        f'<span class="ow-persona" aria-label="Active persona">{escape(choice)}</span>',
        unsafe_allow_html=True,
    )
    return choice
