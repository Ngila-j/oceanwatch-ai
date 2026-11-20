"""Mombasa Port Today — public read-only ops board."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

APP = Path(__file__).resolve().parents[1]
if str(APP) not in sys.path:
    sys.path.insert(0, str(APP))

from components.pagekit import boot, close_page
from components.ui import banner, empty_state, kpi_row

try:
    from services.port_ops_board import PortOpsBoardService
except Exception as exc:  # noqa: BLE001
    boot("Mombasa Port Today", "Public read-only port board.")
    banner("Service unavailable", str(exc), tone="danger")
    close_page()
    st.stop()

DISCLAIMER = (
    "Public decision-support view only. Fuses KPA public shipping list, near-port AIS, "
    "and free marine weather. Not official KPA, KMA, or IMO advice — not a legal or "
    "operational clearance."
)

boot(
    "Mombasa Port Today",
    "Public read-only board — arrivals snapshot, marine conditions, and port pulse.",
    chips=[
        ("Public", "primary"),
        ("Read-only", "info"),
        ("Mombasa", "success"),
    ],
)

st.caption(DISCLAIMER)


@st.cache_data(ttl=120, show_spinner=False)
def _load_pack():
    return PortOpsBoardService().load_pack(
        ais_radius_nm=40.0, ais_hours=36, match_min=0.55
    )


with st.spinner("Loading Mombasa port snapshot…"):
    try:
        pack = _load_pack()
    except Exception as exc:  # noqa: BLE001
        banner("Could not load port board", str(exc), tone="danger")
        close_page()
        st.stop()

k = pack.kpis or {}
wx = pack.weather or {}
marine = pack.marine or {}

kpi_row(
    [
        {
            "label": "KPA vessels",
            "value": str(k.get("kpa_vessels") or 0),
            "hint": f"report {k.get('kpa_report_date') or '—'}",
            "tone": "primary",
        },
        {
            "label": "AIS near-port",
            "value": str(k.get("ais_near") or 0),
            "hint": "40 nm · 36h",
            "tone": "info",
        },
        {
            "label": "KPA↔AIS matches",
            "value": str(k.get("matches") or 0),
            "hint": f"{k.get('match_rate_pct') or 0}% match rate",
            "tone": "success" if (k.get("matches") or 0) else "warning",
        },
        {
            "label": "Board rows",
            "value": str(len(pack.arrival_board) if pack.arrival_board is not None else 0),
            "hint": "arrival board",
            "tone": "info",
        },
    ]
)

if pack.brief:
    st.info(pack.brief)

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Air temp", f"{wx.get('temp_c') or marine.get('temp_c') or '—'} °C")
with c2:
    st.metric(
        "Wind",
        f"{wx.get('wind_kt') or wx.get('wind_speed_kt') or marine.get('wind_kt') or '—'} kt",
    )
with c3:
    st.metric(
        "Wave height",
        f"{marine.get('wave_m') or marine.get('wave_height_m') or wx.get('wave_m') or '—'} m",
    )
with c4:
    st.metric(
        "Conditions",
        str(wx.get("summary") or marine.get("summary") or wx.get("conditions") or "—")[:24],
    )

st.subheader("Arrival board")
board = pack.arrival_board
if board is None or getattr(board, "empty", True):
    empty_state(
        "No arrival rows",
        "KPA list or warehouse tables may be empty right now.",
    )
else:
    show = board.head(30)
    st.dataframe(show, use_container_width=True, hide_index=True)
    st.caption(
        f"Showing top {len(show)} of {len(board)} rows · generated {pack.generated_at or '—'}"
    )

with st.expander("About this board", expanded=False):
    st.markdown(
        """
- **Source mix:** Kenya Ports Authority public movement list, AIS positions near Mombasa,
  optional Open-Meteo weather/marine.
- **Matching:** Vessel names are fuzzy-matched (heuristic) — treat matches as hints.
- **Audience:** Public / partner glance board — no controls, no write paths.
        """
    )
    st.warning(DISCLAIMER)

st.page_link("pages/40_Port_Ops_Board.py", label="Full Port Ops Board (operator) →")
st.page_link("pages/8_Port_Intelligence.py", label="Port Intelligence →")

close_page()
