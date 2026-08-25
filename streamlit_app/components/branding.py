"""Shared attribution, methodology, bandwidth mode, status helpers."""

import streamlit as st


def init_session():
    if "low_bandwidth" not in st.session_state:
        st.session_state.low_bandwidth = False


def bandwidth_toggle():
    init_session()
    st.session_state.low_bandwidth = st.sidebar.checkbox(
        "Low-bandwidth mode",
        value=st.session_state.low_bandwidth,
        help="Prefer numbers and tables; skip heavy charts when possible.",
    )


def is_low_bandwidth() -> bool:
    init_session()
    return bool(st.session_state.low_bandwidth)


def attribution_footer():
    st.markdown("---")
    st.caption(
        "OceanWatch AI · Kenya EEZ / Mombasa focus · Free open-intelligence prototype. "
        "Indicators are decision-support only, not legal or regulatory findings."
    )
    st.caption(
        "Data sources: NOAA CO-OPS · Copernicus Marine Service · "
        "Global Fishing Watch (attribution required; check licence for your use) · "
        "AIS (sample and/or live where available)."
    )
    st.caption(
        "Fishing effort layers powered by Global Fishing Watch — "
        "https://globalfishingwatch.org"
    )
    st.caption("Methodology & limitations: see page **Methodology & Sources**.")


def methodology_blurb():
    st.info(
        "Scores (WIO-OII, port risk, bloom, anomalies) use documented heuristics/models. "
        "Always check **System Health** for data freshness and quality."
    )