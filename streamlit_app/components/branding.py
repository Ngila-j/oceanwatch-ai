"""Shared branding, methodology, bandwidth helpers — thin wrappers over ui."""

from __future__ import annotations

import streamlit as st

from components.ui import a11y_sidebar_controls, ensure_theme, footer_note, sidebar_brand
from ow_theme import apply_theme, init_a11y_defaults

# Re-exports for older pages
__all__ = [
    "init_session",
    "apply_branding",
    "sidebar_controls",
    "bandwidth_toggle",
    "is_low_bandwidth",
    "show_methodology",
    "show_attribution",
    "footer",
    "attribution_footer",
    "methodology_blurb",
]


def init_session() -> None:
    init_a11y_defaults()
    if "low_bandwidth" not in st.session_state:
        st.session_state.low_bandwidth = False


def apply_branding() -> None:
    """Call at the top of multipage scripts that don't go through OceanWatch shell."""
    init_session()
    apply_theme()
    ensure_theme()


def sidebar_controls() -> None:
    """Legacy name used by some pages."""
    with st.sidebar:
        sidebar_brand()
        a11y_sidebar_controls()


def show_methodology(extra: str = "") -> None:
    with st.expander("Methodology & caveats", expanded=False):
        st.markdown(
            """
**OceanWatch AI** is a decision-support prototype for Kenya EEZ / Western Indian Ocean
monitoring. Outputs are indicative, not authoritative.

- AIS and satellite products can lag or contain gaps.
- Risk scores are model-assisted heuristics — always corroborate with primary sources.
- Environmental layers depend on open data availability and refresh cadence.
            """.strip()
        )
        if extra:
            st.markdown(extra)
        st.caption("See **System Health** for data freshness and quality.")


def show_attribution() -> None:
    st.caption(
        "Data sources may include AIS aggregators, Global Fishing Watch, open ocean "
        "color / SST products, and internal OceanWatch pipelines. Attribution on each page."
    )


def footer() -> None:
    footer_note()


def bandwidth_toggle() -> bool:
    """Return low-bandwidth flag without duplicating the sidebar checkbox.

    OceanWatch shell already creates key="low_bandwidth" via a11y_sidebar_controls().
    Creating it again raises StreamlitDuplicateElementKey.
    """
    if "low_bandwidth" not in st.session_state:
        st.session_state.low_bandwidth = False
    # If shell (or prior call) already registered the widget, only read state
    if st.session_state.get("_ow_bw_widget"):
        return bool(st.session_state.low_bandwidth)
    try:
        st.sidebar.checkbox(
            "Low-bandwidth mode",
            key="low_bandwidth",
            help="Hide heavy map layers and large charts when on slow links.",
        )
        st.session_state["_ow_bw_widget"] = True
    except Exception:
        # Duplicate key or no sidebar — keep existing session value
        st.session_state["_ow_bw_widget"] = True
    return bool(st.session_state.low_bandwidth)



def is_low_bandwidth() -> bool:
    """True when the operator enabled low-bandwidth mode."""
    return bool(st.session_state.get("low_bandwidth", False))


# Back-compat aliases used by older pages
def methodology_blurb(extra: str = "") -> None:
    show_methodology(extra)


def attribution_footer() -> None:
    show_attribution()
    footer_note()
